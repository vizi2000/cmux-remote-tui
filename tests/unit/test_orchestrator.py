"""Unit tests for CmuxOrchestrator."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from cmux_remote_tui.application.orchestrator import CmuxOrchestrator
from cmux_remote_tui.domain.models import (
    CmuxTree, Window, Workspace, Pane, Surface, SurfaceRef, SurfaceType,
    ScreenSnapshot, SynthesisContext, SynthesisResult, PerSurfaceState,
    TreeUpdated, SurfaceScreenUpdated, SynthesisReady,
)


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.connected = True
    client.start.return_value = True
    client.stop.return_value = None
    return client


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.provider_name = "test-provider"
    llm.model = "test-model"
    llm.synthesize.return_value = SynthesisResult(
        per_surface=[
            PerSurfaceState(SurfaceRef("s:1"), "claude", "debug", "working", "compiling", 2),
        ],
        global_focus_list=["attach to s:1"],
        raw_text="test analysis",
        timestamp=1.0,
    )
    return llm


@pytest.fixture
def sample_tree():
    s1 = Surface(ref=SurfaceRef("s:1"), title="bash", type=SurfaceType.TERMINAL, tty="/dev/tty1")
    s2 = Surface(ref=SurfaceRef("s:2"), title="vim", type=SurfaceType.TERMINAL, tty="/dev/tty2")
    p1 = Pane(ref="pane:1", surfaces=[s1, s2])
    ws1 = Workspace(ref="ws:1", title="main", panes=[p1], active=True)
    w1 = Window(ref="win:1", workspaces=[ws1])
    return CmuxTree(windows=[w1], active_surface=SurfaceRef("s:1"))


class TestOrchestratorInit:
    def test_init(self, mock_client, mock_llm):
        orch = CmuxOrchestrator(mock_client, mock_llm)
        assert orch._client is mock_client
        assert orch._llm is mock_llm
        assert orch.tree is None

    def test_init_with_callbacks(self, mock_client, mock_llm):
        on_tree = MagicMock()
        on_screen = MagicMock()
        on_synth = MagicMock()
        orch = CmuxOrchestrator(
            mock_client, mock_llm,
            on_tree_updated=on_tree,
            on_screen_updated=on_screen,
            on_synthesis_ready=on_synth,
        )
        assert orch._on_tree_updated is on_tree
        assert orch._on_screen_updated is on_screen
        assert orch._on_synthesis_ready is on_synth


class TestOrchestratorStartStop:
    def test_start_success(self, mock_client, mock_llm, sample_tree):
        mock_client.get_tree.return_value = sample_tree
        orch = CmuxOrchestrator(mock_client, mock_llm)
        result = orch.start()
        assert result is True
        assert orch.connected is True
        mock_client.start.assert_called_once()

    def test_start_failure(self, mock_client, mock_llm):
        mock_client.start.return_value = False
        orch = CmuxOrchestrator(mock_client, mock_llm)
        result = orch.start()
        assert result is False

    def test_stop(self, mock_client, mock_llm):
        orch = CmuxOrchestrator(mock_client, mock_llm)
        orch.stop()
        mock_client.stop.assert_called_once()


class TestOrchestratorTree:
    def test_refresh_tree(self, mock_client, mock_llm, sample_tree):
        mock_client.get_tree.return_value = sample_tree
        orch = CmuxOrchestrator(mock_client, mock_llm)
        orch.refresh_tree()
        assert orch.tree is sample_tree
        mock_client.get_tree.assert_called_once()

    def test_refresh_tree_with_callback(self, mock_client, mock_llm, sample_tree):
        mock_client.get_tree.return_value = sample_tree
        on_tree = MagicMock()
        orch = CmuxOrchestrator(mock_client, mock_llm, on_tree_updated=on_tree)
        orch.refresh_tree()
        on_tree.assert_called_once()
        event = on_tree.call_args[0][0]
        assert isinstance(event, TreeUpdated)
        assert event.tree is sample_tree

    def test_refresh_tree_empty(self, mock_client, mock_llm):
        mock_client.get_tree.return_value = CmuxTree()
        orch = CmuxOrchestrator(mock_client, mock_llm)
        orch.refresh_tree()
        assert orch.tree is not None
        assert len(orch.tree.all_surfaces()) == 0


class TestOrchestratorScreen:
    def test_get_screen(self, mock_client, mock_llm, sample_tree):
        mock_client.get_tree.return_value = sample_tree
        mock_client.read_screen.return_value = ScreenSnapshot(
            ref=SurfaceRef("s:1"), content="hello\nworld", lines=2
        )
        orch = CmuxOrchestrator(mock_client, mock_llm)
        orch.refresh_tree()
        result = orch.get_screen(SurfaceRef("s:1"))
        assert result == "hello\nworld"

    def test_get_screen_none(self, mock_client, mock_llm, sample_tree):
        mock_client.get_tree.return_value = sample_tree
        mock_client.read_screen.return_value = None
        orch = CmuxOrchestrator(mock_client, mock_llm)
        orch.refresh_tree()
        result = orch.get_screen(SurfaceRef("s:999"))
        assert result is None


class TestOrchestratorAttach:
    def test_attach(self, mock_client, mock_llm, sample_tree):
        mock_client.get_tree.return_value = sample_tree
        mock_client.read_screen.return_value = ScreenSnapshot(
            ref=SurfaceRef("s:1"), content="screen data", lines=1
        )
        orch = CmuxOrchestrator(mock_client, mock_llm)
        orch.refresh_tree()
        orch.attach(SurfaceRef("s:1"))
        mock_client.read_screen.assert_called_with(SurfaceRef("s:1"), lines=200)

    def test_attach_with_callback(self, mock_client, mock_llm, sample_tree):
        mock_client.get_tree.return_value = sample_tree
        snap = ScreenSnapshot(ref=SurfaceRef("s:1"), content="data", lines=1)
        mock_client.read_screen.return_value = snap
        on_screen = MagicMock()
        orch = CmuxOrchestrator(mock_client, mock_llm, on_screen_updated=on_screen)
        orch.refresh_tree()
        orch.attach(SurfaceRef("s:1"))
        on_screen.assert_called_once()


class TestOrchestratorSend:
    def test_send_to_surface(self, mock_client, mock_llm, sample_tree):
        mock_client.get_tree.return_value = sample_tree
        mock_client.read_screen.return_value = ScreenSnapshot(
            ref=SurfaceRef("s:1"), content="after send", lines=1
        )
        orch = CmuxOrchestrator(mock_client, mock_llm)
        orch.refresh_tree()
        orch.send_to_surface(SurfaceRef("s:1"), "ls -la")
        mock_client.send_keys.assert_called_once()


class TestOrchestratorSynthesize:
    def test_synthesize(self, mock_client, mock_llm, sample_tree):
        mock_client.get_tree.return_value = sample_tree
        mock_client.read_screen.return_value = ScreenSnapshot(
            ref=SurfaceRef("s:1"), content="compiling...\nDone!", lines=2
        )
        orch = CmuxOrchestrator(mock_client, mock_llm)
        orch.refresh_tree()
        result = orch.synthesize([SurfaceRef("s:1")])
        assert result is not None
        assert isinstance(result, SynthesisResult)
        mock_llm.synthesize.assert_called_once()

    def test_synthesize_with_callback(self, mock_client, mock_llm, sample_tree):
        mock_client.get_tree.return_value = sample_tree
        mock_client.read_screen.return_value = ScreenSnapshot(
            ref=SurfaceRef("s:1"), content="data", lines=1
        )
        on_synth = MagicMock()
        orch = CmuxOrchestrator(mock_client, mock_llm, on_synthesis_ready=on_synth)
        orch.refresh_tree()
        orch.synthesize([SurfaceRef("s:1")])
        on_synth.assert_called_once()
        event = on_synth.call_args[0][0]
        assert isinstance(event, SynthesisReady)

    def test_synthesize_empty_refs(self, mock_client, mock_llm, sample_tree):
        mock_client.get_tree.return_value = sample_tree
        orch = CmuxOrchestrator(mock_client, mock_llm)
        orch.refresh_tree()
        result = orch.synthesize([])
        assert result is None

    def test_synthesize_screen_none(self, mock_client, mock_llm, sample_tree):
        mock_client.get_tree.return_value = sample_tree
        mock_client.read_screen.return_value = None
        orch = CmuxOrchestrator(mock_client, mock_llm)
        orch.refresh_tree()
        result = orch.synthesize([SurfaceRef("s:999")])
        assert result is None

    def test_synthesize_context_notes(self, mock_client, mock_llm, sample_tree):
        mock_client.get_tree.return_value = sample_tree
        mock_client.read_screen.return_value = ScreenSnapshot(
            ref=SurfaceRef("s:1"), content="data", lines=1
        )
        orch = CmuxOrchestrator(mock_client, mock_llm)
        orch.refresh_tree()
        orch.synthesize([SurfaceRef("s:1")], context_notes="GSD phase 3")
        # Verify the prompt was built with context notes
        call_args = mock_llm.synthesize.call_args
        prompt = call_args[0][0]
        assert "GSD phase 3" in prompt


class TestBuildSynthesisPrompt:
    def test_prompt_contains_surface_info(self, mock_client, mock_llm, sample_tree):
        mock_client.get_tree.return_value = sample_tree
        orch = CmuxOrchestrator(mock_client, mock_llm)
        orch.refresh_tree()
        mock_client.read_screen.return_value = ScreenSnapshot(
            ref=SurfaceRef("s:1"), content="test output", lines=1
        )
        orch.synthesize([SurfaceRef("s:1")])
        prompt = mock_llm.synthesize.call_args[0][0]
        assert "s:1" in prompt
        assert "bash" in prompt
        assert "test output" in prompt
        assert "Prioritized Focus List" in prompt
