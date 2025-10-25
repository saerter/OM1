from unittest.mock import AsyncMock, Mock, patch

import pytest

from runtime.multi_mode.config import ModeConfig, ModeSystemConfig
from runtime.multi_mode.cortex import ModeCortexRuntime


@pytest.fixture
def mock_mode_config():
    """Mock mode configuration for testing."""
    mode_config = Mock(spec=ModeConfig)
    mode_config.name = "test_mode"
    mode_config.display_name = "Test Mode"
    mode_config.description = "Test mode for unit testing"
    mode_config.hertz = 2.0
    mode_config.entry_message = "Entering test mode"
    mode_config.exit_message = "Exiting test mode"

    mode_config.load_components = Mock()

    mock_runtime_config = Mock()
    mock_runtime_config.hertz = 2.0
    mock_runtime_config.agent_inputs = []
    mock_runtime_config.cortex_llm = Mock()
    mode_config.to_runtime_config = Mock(return_value=mock_runtime_config)

    return mode_config


@pytest.fixture
def mock_system_config(mock_mode_config):
    """Mock system configuration for testing."""
    config = Mock(spec=ModeSystemConfig)
    config.name = "test_system"
    config.default_mode = "default"
    config.transition_announcement = True
    config.modes = {
        "default": mock_mode_config,
        "advanced": mock_mode_config,
    }
    return config


@pytest.fixture
def mock_mode_manager():
    """Mock mode manager for testing."""
    manager = Mock()
    manager.current_mode_name = "default"
    manager.add_transition_callback = Mock()
    manager.process_tick = AsyncMock(return_value=None)
    return manager


@pytest.fixture
def mock_orchestrators():
    """Mock orchestrators for testing."""
    return {
        "fuser": Mock(),
        "action_orchestrator": Mock(),
        "simulator_orchestrator": Mock(),
        "background_orchestrator": Mock(),
        "input_orchestrator": Mock(),
    }


@pytest.fixture
def cortex_runtime(mock_system_config):
    """ModeCortexRuntime instance for testing."""
    with (
        patch("runtime.multi_mode.cortex.ModeManager") as mock_manager_class,
        patch("runtime.multi_mode.cortex.IOProvider") as mock_io_provider_class,
        patch(
            "runtime.multi_mode.cortex.SleepTickerProvider"
        ) as mock_sleep_provider_class,
    ):
        mock_manager = Mock()
        mock_manager.current_mode_name = "default"
        mock_manager.add_transition_callback = Mock()
        mock_manager_class.return_value = mock_manager

        mock_io_provider = Mock()
        mock_io_provider_class.return_value = mock_io_provider

        mock_sleep_provider = Mock()
        mock_sleep_provider.skip_sleep = False
        mock_sleep_provider_class.return_value = mock_sleep_provider

        runtime = ModeCortexRuntime(mock_system_config)
        runtime.mode_manager = mock_manager
        runtime.io_provider = mock_io_provider
        runtime.sleep_ticker_provider = mock_sleep_provider

        return runtime, {
            "mode_manager": mock_manager,
            "io_provider": mock_io_provider,
            "sleep_provider": mock_sleep_provider,
        }


class TestModeCortexRuntime:
    """Test cases for ModeCortexRuntime class."""

    def test_initialization(self, mock_system_config):
        """Test cortex runtime initialization."""
        with (
            patch("runtime.multi_mode.cortex.ModeManager") as mock_manager_class,
            patch("runtime.multi_mode.cortex.IOProvider"),
            patch("runtime.multi_mode.cortex.SleepTickerProvider"),
        ):
            mock_manager = Mock()
            mock_manager.add_transition_callback = Mock()
            mock_manager_class.return_value = mock_manager

            runtime = ModeCortexRuntime(mock_system_config)

            assert runtime.mode_config == mock_system_config
            assert runtime.current_config is None
            assert runtime.fuser is None
            assert runtime.action_orchestrator is None
            assert runtime.simulator_orchestrator is None
            assert runtime.background_orchestrator is None
            assert runtime.input_orchestrator is None
            assert runtime._mode_initialized is False

            mock_manager.add_transition_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_mode(self, cortex_runtime, mock_mode_config):
        """Test mode initialization."""
        runtime, mocks = cortex_runtime

        with (
            patch("runtime.multi_mode.cortex.Fuser") as mock_fuser_class,
            patch("runtime.multi_mode.cortex.ActionOrchestrator") as mock_action_class,
            patch(
                "runtime.multi_mode.cortex.SimulatorOrchestrator"
            ) as mock_simulator_class,
            patch(
                "runtime.multi_mode.cortex.BackgroundOrchestrator"
            ) as mock_background_class,
        ):
            mock_fuser = Mock()
            mock_action_orch = Mock()
            mock_simulator_orch = Mock()
            mock_background_orch = Mock()

            mock_fuser_class.return_value = mock_fuser
            mock_action_class.return_value = mock_action_orch
            mock_simulator_class.return_value = mock_simulator_orch
            mock_background_class.return_value = mock_background_orch

            runtime.mode_config.modes = {"test_mode": mock_mode_config}

            await runtime._initialize_mode("test_mode")

            mock_mode_config.load_components.assert_called_once_with(
                runtime.mode_config
            )
            mock_mode_config.to_runtime_config.assert_called_once_with(
                runtime.mode_config
            )

            assert runtime.fuser == mock_fuser
            assert runtime.action_orchestrator == mock_action_orch
            assert runtime.simulator_orchestrator == mock_simulator_orch
            assert runtime.background_orchestrator == mock_background_orch

    @pytest.mark.asyncio
    async def test_on_mode_transition(self, cortex_runtime):
        """Test mode transition handling."""
        runtime, mocks = cortex_runtime

        with (
            patch.object(runtime, "_stop_current_orchestrators") as mock_stop,
            patch.object(runtime, "_initialize_mode") as mock_init,
            patch.object(runtime, "_start_orchestrators") as mock_start,
            patch("runtime.multi_mode.cortex.ElevenLabsTTSProvider") as mock_tts_class,
        ):
            mock_tts = Mock()
            mock_tts.add_pending_message = Mock()
            mock_tts_class.return_value = mock_tts

            mock_from_mode = Mock()
            mock_from_mode.exit_message = "Exiting previous mode"
            mock_to_mode = Mock()
            mock_to_mode.entry_message = "Welcome to new mode"
            runtime.mode_config.modes = {
                "from_mode": mock_from_mode,
                "to_mode": mock_to_mode,
            }

            await runtime._on_mode_transition("from_mode", "to_mode")

            mock_stop.assert_called_once()
            mock_init.assert_called_once_with("to_mode")
            mock_start.assert_called_once()
            assert mock_tts.add_pending_message.call_count == 2
            mock_tts.add_pending_message.assert_any_call("Exiting previous mode")
            mock_tts.add_pending_message.assert_any_call("Welcome to new mode")

    @pytest.mark.asyncio
    async def test_on_mode_transition_no_announcement(self, cortex_runtime):
        """Test mode transition without announcement."""
        runtime, mocks = cortex_runtime
        runtime.mode_config.transition_announcement = False

        with (
            patch.object(runtime, "_stop_current_orchestrators"),
            patch.object(runtime, "_initialize_mode"),
            patch.object(runtime, "_start_orchestrators"),
            patch("runtime.multi_mode.cortex.ElevenLabsTTSProvider") as mock_tts_class,
        ):
            mock_tts = Mock()
            mock_tts.add_pending_message = Mock()
            mock_tts_class.return_value = mock_tts

            mock_mode = Mock()
            mock_mode.entry_message = "Welcome"
            runtime.mode_config.modes = {"to_mode": mock_mode}

            await runtime._on_mode_transition("from_mode", "to_mode")

            mock_tts.add_pending_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_mode_transition_exception(self, cortex_runtime):
        """Test mode transition with exception handling."""
        runtime, mocks = cortex_runtime

        mock_from_mode = Mock()
        mock_from_mode.exit_message = "Exiting previous mode"
        mock_to_mode = Mock()
        mock_to_mode.entry_message = "Welcome to new mode"
        runtime.mode_config.modes = {
            "from_mode": mock_from_mode,
            "to_mode": mock_to_mode,
        }

        with patch.object(
            runtime, "_stop_current_orchestrators", side_effect=Exception("Test error")
        ):
            with pytest.raises(Exception, match="Test error"):
                await runtime._on_mode_transition("from_mode", "to_mode")

    @pytest.mark.asyncio
    async def test_stop_current_orchestrators(self, cortex_runtime):
        """Test stopping current orchestrators."""
        runtime, mocks = cortex_runtime

        mock_input_task = Mock()
        mock_input_task.done.return_value = False
        mock_input_task.cancel = Mock()

        mock_simulator_task = Mock()
        mock_simulator_task.done.return_value = False
        mock_simulator_task.cancel = Mock()

        mock_action_task = Mock()
        mock_action_task.done.return_value = False
        mock_action_task.cancel = Mock()

        mock_background_task = Mock()
        mock_background_task.done.return_value = False
        mock_background_task.cancel = Mock()

        runtime.input_listener_task = mock_input_task
        runtime.simulator_task = mock_simulator_task
        runtime.action_task = mock_action_task
        runtime.background_task = mock_background_task

        with patch("asyncio.gather", new_callable=AsyncMock) as mock_gather:
            await runtime._stop_current_orchestrators()

            mock_input_task.cancel.assert_called_once()
            mock_simulator_task.cancel.assert_called_once()
            mock_action_task.cancel.assert_called_once()
            mock_background_task.cancel.assert_called_once()

            mock_gather.assert_called_once()

            assert runtime.input_listener_task is None
            assert runtime.simulator_task is None
            assert runtime.action_task is None
            assert runtime.background_task is None

    @pytest.mark.asyncio
    async def test_stop_current_orchestrators_done_tasks(self, cortex_runtime):
        """Test stopping orchestrators with already done tasks."""
        runtime, mocks = cortex_runtime

        mock_task = Mock()
        mock_task.done.return_value = True
        mock_task.cancel = Mock()

        runtime.input_listener_task = mock_task

        with patch("asyncio.gather", new_callable=AsyncMock) as mock_gather:
            await runtime._stop_current_orchestrators()

            mock_task.cancel.assert_not_called()
            mock_gather.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_orchestrators_no_config(self, cortex_runtime):
        """Test starting orchestrators without current config raises error."""
        runtime, mocks = cortex_runtime
        runtime.current_config = None

        with pytest.raises(RuntimeError, match="No current config available"):
            await runtime._start_orchestrators()

    @pytest.mark.asyncio
    async def test_cleanup_tasks(self, cortex_runtime):
        """Test cleanup of all tasks."""
        runtime, mocks = cortex_runtime

        mock_task1 = Mock()
        mock_task1.done.return_value = False
        mock_task1.cancel = Mock()

        mock_task2 = Mock()
        mock_task2.done.return_value = False
        mock_task2.cancel = Mock()

        runtime.input_listener_task = mock_task1
        runtime.simulator_task = mock_task2

        with patch("asyncio.gather", new_callable=AsyncMock) as mock_gather:
            await runtime._cleanup_tasks()

            mock_task1.cancel.assert_called_once()
            mock_task2.cancel.assert_called_once()
            mock_gather.assert_called_once()


class TestModeTransitionRecovery:
    """Test cases for mode transition recovery mechanism."""

    @pytest.mark.asyncio
    async def test_create_backup_state(self, cortex_runtime):
        """Test backup state creation."""
        runtime, mocks = cortex_runtime
        
        mock_config = Mock()
        runtime.current_config = mock_config
        
        runtime._create_backup_state("test_mode")
        
        assert runtime._backup_mode_name == "test_mode"
        assert runtime._backup_config == mock_config

    @pytest.mark.asyncio
    async def test_clear_backup_state(self, cortex_runtime):
        """Test backup state clearing."""
        runtime, mocks = cortex_runtime
        
        runtime._backup_mode_name = "test_mode"
        runtime._backup_config = Mock()
        
        runtime._clear_backup_state()
        
        assert runtime._backup_mode_name is None
        assert runtime._backup_config is None

    @pytest.mark.asyncio
    async def test_rollback_to_backup_success(self, cortex_runtime):
        """Test successful rollback to backup mode."""
        runtime, mocks = cortex_runtime
        
        # Setup backup state
        mock_backup_config = Mock()
        mock_backup_config.agent_inputs = []
        runtime._backup_mode_name = "backup_mode"
        runtime._backup_config = mock_backup_config
        
        with (
            patch.object(runtime, "_stop_current_orchestrators") as mock_stop,
            patch.object(runtime, "_start_orchestrators") as mock_start,
            patch("runtime.multi_mode.cortex.Fuser") as mock_fuser_class,
            patch("runtime.multi_mode.cortex.ActionOrchestrator") as mock_action_class,
            patch("runtime.multi_mode.cortex.SimulatorOrchestrator") as mock_simulator_class,
            patch("runtime.multi_mode.cortex.BackgroundOrchestrator") as mock_background_class,
        ):
            await runtime._rollback_to_backup()
            
            mock_stop.assert_called_once()
            mock_start.assert_called_once()
            assert runtime.current_config == mock_backup_config
            assert runtime.mode_manager.state.current_mode == "backup_mode"

    @pytest.mark.asyncio
    async def test_rollback_to_backup_no_backup(self, cortex_runtime):
        """Test rollback fails when no backup exists."""
        runtime, mocks = cortex_runtime
        
        runtime._backup_mode_name = None
        
        with pytest.raises(RuntimeError, match="No backup state available"):
            await runtime._rollback_to_backup()

    @pytest.mark.asyncio
    async def test_emergency_mode_recovery(self, cortex_runtime, mock_mode_config):
        """Test emergency mode recovery."""
        runtime, mocks = cortex_runtime
        
        with (
            patch.object(runtime, "_stop_current_orchestrators") as mock_stop,
            patch.object(runtime, "_initialize_mode") as mock_init,
            patch.object(runtime, "_start_orchestrators") as mock_start,
        ):
            await runtime._emergency_mode_recovery("safe_mode")
            
            mock_stop.assert_called_once()
            mock_init.assert_called_once_with("safe_mode")
            mock_start.assert_called_once()
            assert runtime.mode_manager.state.current_mode == "safe_mode"
            assert runtime.mode_manager.state.previous_mode is None

    @pytest.mark.asyncio
    async def test_handle_transition_failure_rollback_success(self, cortex_runtime):
        """Test transition failure with successful rollback."""
        runtime, mocks = cortex_runtime
        
        runtime._backup_mode_name = "previous_mode"
        runtime._backup_config = Mock()
        
        with (
            patch.object(runtime, "_rollback_to_backup") as mock_rollback,
            patch("runtime.multi_mode.cortex.ElevenLabsTTSProvider") as mock_tts_class,
        ):
            mock_tts = Mock()
            mock_tts.add_pending_message = Mock()
            mock_tts_class.return_value = mock_tts
            
            test_error = Exception("Transition failed")
            await runtime._handle_transition_failure("from_mode", "to_mode", test_error)
            
            mock_rollback.assert_called_once()
            mock_tts.add_pending_message.assert_called_once_with(
                "Mode transition failed. Returning to previous mode."
            )

    @pytest.mark.asyncio
    async def test_handle_transition_failure_rollback_fails_emergency_recovery(
        self, cortex_runtime
    ):
        """Test transition failure with rollback failure, then emergency recovery."""
        runtime, mocks = cortex_runtime
        
        runtime._backup_mode_name = "previous_mode"
        runtime.mode_config.default_mode = "default"
        
        with (
            patch.object(
                runtime, "_rollback_to_backup", side_effect=Exception("Rollback failed")
            ) as mock_rollback,
            patch.object(runtime, "_emergency_mode_recovery") as mock_emergency,
            patch("runtime.multi_mode.cortex.ElevenLabsTTSProvider") as mock_tts_class,
        ):
            mock_tts = Mock()
            mock_tts.add_pending_message = Mock()
            mock_tts_class.return_value = mock_tts
            
            test_error = Exception("Transition failed")
            await runtime._handle_transition_failure("from_mode", "to_mode", test_error)
            
            mock_rollback.assert_called_once()
            mock_emergency.assert_called_once_with("default")
            mock_tts.add_pending_message.assert_called_once_with(
                "Mode transition failed. Switching to safe mode."
            )

    @pytest.mark.asyncio
    async def test_handle_transition_failure_all_recovery_fails(self, cortex_runtime):
        """Test transition failure when all recovery attempts fail."""
        runtime, mocks = cortex_runtime
        
        runtime._backup_mode_name = "previous_mode"
        runtime.mode_config.default_mode = "default"
        
        with (
            patch.object(
                runtime, "_rollback_to_backup", side_effect=Exception("Rollback failed")
            ),
            patch.object(
                runtime,
                "_emergency_mode_recovery",
                side_effect=Exception("Emergency recovery failed"),
            ),
            patch("runtime.multi_mode.cortex.ElevenLabsTTSProvider") as mock_tts_class,
        ):
            mock_tts = Mock()
            mock_tts.add_pending_message = Mock()
            mock_tts_class.return_value = mock_tts
            
            test_error = Exception("Transition failed")
            
            with pytest.raises(
                RuntimeError,
                match="Failed to transition to to_mode and all recovery attempts failed",
            ):
                await runtime._handle_transition_failure(
                    "from_mode", "to_mode", test_error
                )
            
            # Should have called both TTS messages
            assert mock_tts.add_pending_message.call_count == 1
            mock_tts.add_pending_message.assert_called_with(
                "Critical error: unable to recover mode. Please restart the system."
            )

    @pytest.mark.asyncio
    async def test_on_mode_transition_with_recovery(self, cortex_runtime):
        """Test mode transition that fails and recovers."""
        runtime, mocks = cortex_runtime
        
        mock_from_mode = Mock()
        mock_from_mode.exit_message = "Exiting"
        runtime.mode_config.modes = {"from_mode": mock_from_mode, "to_mode": Mock()}
        
        with (
            patch.object(runtime, "_stop_current_orchestrators"),
            patch.object(
                runtime, "_initialize_mode", side_effect=Exception("Init failed")
            ),
            patch.object(runtime, "_handle_transition_failure") as mock_handle_failure,
        ):
            await runtime._on_mode_transition("from_mode", "to_mode")
            
            mock_handle_failure.assert_called_once()
            assert runtime._transition_in_progress is False

    @pytest.mark.asyncio
    async def test_concurrent_transition_prevention(self, cortex_runtime):
        """Test that concurrent transitions are prevented."""
        runtime, mocks = cortex_runtime
        
        runtime._transition_in_progress = True
        
        with (
            patch.object(runtime, "_stop_current_orchestrators") as mock_stop,
        ):
            await runtime._on_mode_transition("from_mode", "to_mode")
            
            # Should not have attempted to stop orchestrators
            mock_stop.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_transition_clears_backup(self, cortex_runtime):
        """Test that successful transition clears backup state."""
        runtime, mocks = cortex_runtime
        
        mock_from_mode = Mock()
        mock_from_mode.exit_message = "Exiting"
        mock_to_mode = Mock()
        mock_to_mode.entry_message = "Entering"
        runtime.mode_config.modes = {"from_mode": mock_from_mode, "to_mode": mock_to_mode}
        
        with (
            patch.object(runtime, "_stop_current_orchestrators"),
            patch.object(runtime, "_initialize_mode"),
            patch.object(runtime, "_start_orchestrators"),
            patch.object(runtime, "_clear_backup_state") as mock_clear,
            patch("runtime.multi_mode.cortex.ElevenLabsTTSProvider"),
        ):
            await runtime._on_mode_transition("from_mode", "to_mode")
            
            mock_clear.assert_called_once()
            assert runtime._transition_in_progress is False
