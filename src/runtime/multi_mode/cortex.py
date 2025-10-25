import asyncio
import logging
from typing import List, Optional, Union

from actions.orchestrator import ActionOrchestrator
from backgrounds.orchestrator import BackgroundOrchestrator
from fuser import Fuser
from inputs.orchestrator import InputOrchestrator
from providers.elevenlabs_tts_provider import ElevenLabsTTSProvider
from providers.io_provider import IOProvider
from providers.sleep_ticker_provider import SleepTickerProvider
from runtime.multi_mode.config import ModeSystemConfig, RuntimeConfig
from runtime.multi_mode.manager import ModeManager
from simulators.orchestrator import SimulatorOrchestrator


class ModeCortexRuntime:
    """
    Mode-aware cortex runtime that can dynamically switch between different
    operational modes, each with their own configuration, inputs, and actions.
    """

    def __init__(self, mode_config: ModeSystemConfig):
        """
        Initialize the mode-aware cortex runtime.

        Parameters
        ----------
        mode_config : ModeSystemConfig
            The complete mode system configuration
        """
        self.mode_config = mode_config
        self.mode_manager = ModeManager(mode_config)
        self.io_provider = IOProvider()
        self.sleep_ticker_provider = SleepTickerProvider()

        # Current runtime components
        self.current_config: Optional[RuntimeConfig] = None
        self.fuser: Optional[Fuser] = None
        self.action_orchestrator: Optional[ActionOrchestrator] = None
        self.simulator_orchestrator: Optional[SimulatorOrchestrator] = None
        self.background_orchestrator: Optional[BackgroundOrchestrator] = None
        self.input_orchestrator: Optional[InputOrchestrator] = None

        # Tasks for orchestrators
        self.input_listener_task: Optional[asyncio.Task] = None
        self.simulator_task: Optional[asyncio.Future] = None
        self.action_task: Optional[asyncio.Future] = None
        self.background_task: Optional[asyncio.Future] = None

        # Backup state for recovery mechanism
        self._backup_config: Optional[RuntimeConfig] = None
        self._backup_mode_name: Optional[str] = None
        self._transition_in_progress = False

        # Setup transition callback
        self.mode_manager.add_transition_callback(self._on_mode_transition)

        # Flag to track if mode is initialized
        self._mode_initialized = False

    async def _initialize_mode(self, mode_name: str):
        """
        Initialize the runtime with a specific mode.

        Parameters
        ----------
        mode_name : str
            The name of the mode to initialize
        """
        mode_config = self.mode_config.modes[mode_name]

        mode_config.load_components(self.mode_config)

        self.current_config = mode_config.to_runtime_config(self.mode_config)

        logging.info(f"Initializing mode: {mode_config.display_name}")

        self.fuser = Fuser(self.current_config)
        self.action_orchestrator = ActionOrchestrator(self.current_config)
        self.simulator_orchestrator = SimulatorOrchestrator(self.current_config)
        self.background_orchestrator = BackgroundOrchestrator(self.current_config)

        logging.info(f"Mode '{mode_name}' initialized successfully")

    async def _on_mode_transition(self, from_mode: str, to_mode: str):
        """
        Handle mode transitions by gracefully stopping current components
        and starting new ones for the target mode.

        Parameters
        ----------
        from_mode : str
            The name of the mode being transitioned from
        to_mode : str
            The name of the mode being transitioned to
        """
        logging.info(f"Handling mode transition: {from_mode} -> {to_mode}")

        # Prevent concurrent transitions
        if self._transition_in_progress:
            logging.warning("Transition already in progress, skipping")
            return

        self._transition_in_progress = True

        try:
            # Create backup of current state before transition
            self._create_backup_state(from_mode)

            # Play exit message if enabled
            if self.mode_config.transition_announcement:
                from_config = self.mode_config.modes[from_mode]
                if from_config.exit_message:
                    ElevenLabsTTSProvider().add_pending_message(
                        from_config.exit_message
                    )
                    logging.info(f"Mode exit: {from_config.exit_message}")

            # Stop current orchestrators
            await self._stop_current_orchestrators()

            # Load new mode configuration
            await self._initialize_mode(to_mode)

            # Start new orchestrators
            await self._start_orchestrators()

            # Play transition messages if enabled
            if self.mode_config.transition_announcement:
                to_config = self.mode_config.modes[to_mode]
                if to_config.entry_message:
                    ElevenLabsTTSProvider().add_pending_message(to_config.entry_message)
                    logging.info(f"Mode entry: {to_config.entry_message}")

            logging.info(f"Successfully transitioned to mode: {to_mode}")
            # Clear backup on successful transition
            self._clear_backup_state()

        except Exception as e:
            logging.error(f"Error during mode transition {from_mode} -> {to_mode}: {e}")
            # Implement fallback/recovery mechanism
            await self._handle_transition_failure(from_mode, to_mode, e)

        finally:
            self._transition_in_progress = False

    async def _handle_transition_failure(
        self, from_mode: str, to_mode: str, error: Exception
    ):
        """
        Handle transition failures with a multi-stage recovery strategy.

        Parameters
        ----------
        from_mode : str
            The mode we were transitioning from
        to_mode : str
            The mode we failed to transition to
        error : Exception
            The exception that caused the failure
        """
        logging.error(
            f"Initiating recovery from failed transition {from_mode} -> {to_mode}"
        )

        # Stage 1: Try to rollback to previous mode
        if self._backup_mode_name and self._backup_mode_name != to_mode:
            logging.info(f"Attempting rollback to previous mode: {self._backup_mode_name}")
            try:
                await self._rollback_to_backup()
                logging.info(
                    f"Successfully rolled back to mode: {self._backup_mode_name}"
                )
                ElevenLabsTTSProvider().add_pending_message(
                    "Mode transition failed. Returning to previous mode."
                )
                return
            except Exception as rollback_error:
                logging.error(
                    f"Rollback to {self._backup_mode_name} failed: {rollback_error}"
                )

        # Stage 2: Try to transition to default safe mode
        default_mode = self.mode_config.default_mode
        if default_mode != to_mode and default_mode != from_mode:
            logging.info(f"Attempting recovery to default mode: {default_mode}")
            try:
                await self._emergency_mode_recovery(default_mode)
                logging.info(f"Successfully recovered to default mode: {default_mode}")
                ElevenLabsTTSProvider().add_pending_message(
                    "Mode transition failed. Switching to safe mode."
                )
                return
            except Exception as default_error:
                logging.error(
                    f"Recovery to default mode {default_mode} failed: {default_error}"
                )

        # Stage 3: Critical failure - try to maintain minimal functionality
        logging.critical(
            "All recovery attempts failed. System may be in unstable state."
        )
        ElevenLabsTTSProvider().add_pending_message(
            "Critical error: unable to recover mode. Please restart the system."
        )
        raise RuntimeError(
            f"Failed to transition to {to_mode} and all recovery attempts failed"
        ) from error

    def _create_backup_state(self, mode_name: str):
        """
        Create a backup of the current mode state for potential rollback.

        Parameters
        ----------
        mode_name : str
            The name of the mode to backup
        """
        logging.debug(f"Creating backup of mode: {mode_name}")
        self._backup_mode_name = mode_name
        self._backup_config = self.current_config
        logging.debug(f"Backup created for mode: {mode_name}")

    def _clear_backup_state(self):
        """Clear the backup state after a successful transition."""
        logging.debug("Clearing backup state")
        self._backup_mode_name = None
        self._backup_config = None

    async def _rollback_to_backup(self):
        """
        Rollback to the previously backed up mode state.

        Raises
        ------
        RuntimeError
            If no backup state is available
        """
        if not self._backup_mode_name:
            raise RuntimeError("No backup state available for rollback")

        logging.info(f"Rolling back to backup mode: {self._backup_mode_name}")

        # Stop any partially initialized orchestrators
        await self._stop_current_orchestrators()

        # Restore backup configuration
        self.current_config = self._backup_config
        mode_name = self._backup_mode_name

        # Reinitialize orchestrators with backup config
        if self.current_config:
            self.fuser = Fuser(self.current_config)
            self.action_orchestrator = ActionOrchestrator(self.current_config)
            self.simulator_orchestrator = SimulatorOrchestrator(self.current_config)
            self.background_orchestrator = BackgroundOrchestrator(self.current_config)

        # Restart orchestrators
        await self._start_orchestrators()

        # Update mode manager to reflect rollback
        self.mode_manager.state.current_mode = mode_name
        logging.info(f"Successfully rolled back to mode: {mode_name}")

    async def _emergency_mode_recovery(self, safe_mode: str):
        """
        Emergency recovery to a safe mode when rollback fails.

        Parameters
        ----------
        safe_mode : str
            The name of the safe mode to recover to
        """
        logging.warning(f"Initiating emergency recovery to safe mode: {safe_mode}")

        # Stop all current orchestrators
        await self._stop_current_orchestrators()

        # Initialize safe mode from scratch
        await self._initialize_mode(safe_mode)

        # Start orchestrators
        await self._start_orchestrators()

        # Update mode manager
        self.mode_manager.state.current_mode = safe_mode
        self.mode_manager.state.previous_mode = None
        logging.info(f"Emergency recovery to {safe_mode} completed")

    async def _stop_current_orchestrators(self):
        """
        Stop all current orchestrator tasks gracefully.
        """
        logging.debug("Stopping current orchestrators...")

        tasks_to_cancel = []

        if self.input_listener_task and not self.input_listener_task.done():
            logging.debug("Cancelling input listener task")
            tasks_to_cancel.append(self.input_listener_task)

        if self.simulator_task and not self.simulator_task.done():
            logging.debug("Cancelling simulator task")
            tasks_to_cancel.append(self.simulator_task)

        if self.action_task and not self.action_task.done():
            logging.debug("Cancelling action task")
            tasks_to_cancel.append(self.action_task)

        if self.background_task and not self.background_task.done():
            logging.debug("Cancelling background task")
            tasks_to_cancel.append(self.background_task)

        # Cancel all tasks
        for task in tasks_to_cancel:
            task.cancel()

        # Wait for cancellations to complete
        if tasks_to_cancel:
            try:
                await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
                logging.debug(
                    f"Successfully cancelled {len(tasks_to_cancel)} orchestrator tasks"
                )
            except Exception as e:
                logging.warning(f"Error during orchestrator shutdown: {e}")

        # Clear task references
        self.input_listener_task = None
        self.simulator_task = None
        self.action_task = None
        self.background_task = None

        logging.debug("Orchestrators stopped successfully")

    async def _start_orchestrators(self):
        """
        Start orchestrators for the current mode.
        """
        if not self.current_config:
            raise RuntimeError("No current config available")

        # Start input listener
        self.input_orchestrator = InputOrchestrator(self.current_config.agent_inputs)
        self.input_listener_task = asyncio.create_task(self.input_orchestrator.listen())

        # Start other orchestrators
        if self.simulator_orchestrator:
            self.simulator_task = self.simulator_orchestrator.start()
        if self.action_orchestrator:
            self.action_task = self.action_orchestrator.start()
        if self.background_orchestrator:
            self.background_task = self.background_orchestrator.start()

        logging.debug("Orchestrators started successfully")

    async def _cleanup_tasks(self):
        """
        Cleanup all running tasks gracefully.
        """
        tasks_to_cancel = []

        if self.input_listener_task and not self.input_listener_task.done():
            tasks_to_cancel.append(self.input_listener_task)

        if self.simulator_task and not self.simulator_task.done():
            tasks_to_cancel.append(self.simulator_task)

        if self.action_task and not self.action_task.done():
            tasks_to_cancel.append(self.action_task)

        if self.background_task and not self.background_task.done():
            tasks_to_cancel.append(self.background_task)

        # Cancel all tasks
        for task in tasks_to_cancel:
            task.cancel()

        # Wait for cancellations to complete
        if tasks_to_cancel:
            try:
                await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
            except Exception as e:
                logging.warning(f"Error during final cleanup: {e}")

        logging.debug("Tasks cleaned up successfully")

    async def run(self) -> None:
        """
        Start the mode-aware runtime's main execution loop.
        """
        try:
            self.mode_manager.set_event_loop(asyncio.get_event_loop())

            if not self._mode_initialized:
                await self._initialize_mode(self.mode_manager.current_mode_name)
                self._mode_initialized = True

                # Play initial mode entry message if enabled
                if self.mode_config.transition_announcement:
                    initial_mode_config = self.mode_config.modes[
                        self.mode_manager.current_mode_name
                    ]
                    if initial_mode_config.entry_message:
                        ElevenLabsTTSProvider().add_pending_message(
                            initial_mode_config.entry_message
                        )
                        logging.info(
                            f"Initial mode entry: {initial_mode_config.entry_message}"
                        )

            await self._start_orchestrators()

            cortex_loop_task = asyncio.create_task(self._run_cortex_loop())

            while True:
                try:
                    awaitables: List[Union[asyncio.Task, asyncio.Future]] = [
                        cortex_loop_task
                    ]
                    if self.input_listener_task and not self.input_listener_task.done():
                        awaitables.append(self.input_listener_task)
                    if self.simulator_task and not self.simulator_task.done():
                        awaitables.append(self.simulator_task)
                    if self.action_task and not self.action_task.done():
                        awaitables.append(self.action_task)
                    if self.background_task and not self.background_task.done():
                        awaitables.append(self.background_task)

                    await asyncio.gather(*awaitables)

                except asyncio.CancelledError:
                    logging.debug(
                        "Tasks cancelled during mode transition, continuing..."
                    )

                    await asyncio.sleep(0.1)

                    if not cortex_loop_task.done():
                        continue
                    else:
                        break

                except Exception as e:
                    logging.error(f"Error in orchestrator tasks: {e}")
                    await asyncio.sleep(1.0)

        except Exception as e:
            logging.error(f"Error in mode-aware cortex runtime: {e}")
            raise
        finally:
            await self._cleanup_tasks()

    async def _run_cortex_loop(self) -> None:
        """
        Execute the main cortex processing loop with mode awareness.
        """
        while True:
            try:
                if not self.sleep_ticker_provider.skip_sleep and self.current_config:
                    await self.sleep_ticker_provider.sleep(
                        1 / self.current_config.hertz
                    )

                await self._tick()
                self.sleep_ticker_provider.skip_sleep = False

            except Exception as e:
                logging.error(f"Error in cortex loop: {e}")
                await asyncio.sleep(1.0)

    async def _tick(self) -> None:
        """
        Execute a single tick of the mode-aware cortex processing cycle.
        """
        if not self.current_config or not self.fuser or not self.action_orchestrator:
            logging.warning("Cortex not properly initialized, skipping tick")
            return

        finished_promises, _ = await self.action_orchestrator.flush_promises()

        prompt = self.fuser.fuse(self.current_config.agent_inputs, finished_promises)
        if prompt is None:
            logging.debug("No prompt to fuse")
            return

        with self.io_provider.mode_transition_input():
            last_input = self.io_provider.get_mode_transition_input()
        new_mode = await self.mode_manager.process_tick(last_input)
        if new_mode:
            logging.info(f"Mode switched to: {new_mode}")
            return

        output = await self.current_config.cortex_llm.ask(prompt)
        if output is None:
            logging.debug("No output from LLM")
            return

        if self.simulator_orchestrator:
            await self.simulator_orchestrator.promise(output.actions)

        await self.action_orchestrator.promise(output.actions)

    def get_mode_info(self) -> dict:
        """
        Get information about the current mode and available transitions.
        """
        return self.mode_manager.get_mode_info()

    async def request_mode_change(self, target_mode: str) -> bool:
        """
        Request a manual mode change.

        Parameters
        ----------
        target_mode : str
            The name of the target mode

        Returns
        -------
        bool
            True if the transition was successful, False otherwise
        """
        return await self.mode_manager.request_transition(target_mode, "manual")

    def get_available_modes(self) -> dict:
        """
        Get information about all available modes.

        Returns
        -------
        dict
            Dictionary mapping mode names to their display information
        """
        return {
            name: {
                "display_name": config.display_name,
                "description": config.description,
                "is_current": name == self.mode_manager.current_mode_name,
            }
            for name, config in self.mode_config.modes.items()
        }
