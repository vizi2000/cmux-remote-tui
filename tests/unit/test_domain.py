"""Unit tests for domain models."""
import pytest
from cmux_remote_tui.domain.models import (
    CmuxTree, Window, Workspace, Pane, Surface, SurfaceRef, SurfaceType,
    ScreenSnapshot, SurfaceContext, SynthesisContext, SynthesisResult, PerSurfaceState,
    TreeUpdated, SurfaceScreenUpdated, SynthesisReady,
)


class TestSurfaceRef:
    def test_creation(self):
        ref = SurfaceRef("surface:42")
        assert ref.value == "surface:42"

    def test_str(self):
        ref = SurfaceRef("surface:1")
        assert str(ref) == "surface:1"

    def test_equality(self):
        r1 = SurfaceRef("surface:1")
        r2 = SurfaceRef("surface:1")
        r3 = SurfaceRef("surface:2")
        assert r1 == r2
        assert r1 != r3

    def test_hashable(self):
        refs = {SurfaceRef("surface:1"), SurfaceRef("surface:2"), SurfaceRef("surface:1")}
        assert len(refs) == 2

    def test_frozen(self):
        ref = SurfaceRef("surface:1")
        with pytest.raises(AttributeError):
            ref.value = "surface:2"


class TestSurface:
    def test_terminal_creation(self):
        s = Surface(ref=SurfaceRef("s:1"), title="bash", type=SurfaceType.TERMINAL)
        assert s.is_terminal
        assert not s.is_browser
        assert s.title == "bash"

    def test_browser_creation(self):
        s = Surface(ref=SurfaceRef("s:2"), title="Chrome", type=SurfaceType.BROWSER, url="https://example.com")
        assert s.is_browser
        assert not s.is_terminal
        assert s.url == "https://example.com"

    def test_frozen(self):
        s = Surface(ref=SurfaceRef("s:1"), title="test", type=SurfaceType.TERMINAL)
        with pytest.raises(AttributeError):
            s.title = "changed"


class TestCmuxTree:
    def test_empty_tree(self):
        tree = CmuxTree()
        assert tree.windows == []
        assert tree.active_surface is None
        assert tree.all_surfaces() == []

    def test_single_surface(self):
        s = Surface(ref=SurfaceRef("s:1"), title="bash", type=SurfaceType.TERMINAL)
        p = Pane(ref="pane:1", surfaces=[s])
        ws = Workspace(ref="ws:1", title="main", panes=[p])
        w = Window(ref="win:1", workspaces=[ws])
        tree = CmuxTree(windows=[w], active_surface=SurfaceRef("s:1"))

        assert len(tree.windows) == 1
        assert tree.active_surface == SurfaceRef("s:1")
        assert len(tree.all_surfaces()) == 1

    def test_multiple_surfaces(self):
        s1 = Surface(ref=SurfaceRef("s:1"), title="bash", type=SurfaceType.TERMINAL)
        s2 = Surface(ref=SurfaceRef("s:2"), title="vim", type=SurfaceType.TERMINAL)
        s3 = Surface(ref=SurfaceRef("s:3"), title="Chrome", type=SurfaceType.BROWSER, url="https://x.com")
        p1 = Pane(ref="pane:1", surfaces=[s1, s2])
        p2 = Pane(ref="pane:2", surfaces=[s3])
        ws = Workspace(ref="ws:1", title="dev", panes=[p1, p2])
        w = Window(ref="win:1", workspaces=[ws])
        tree = CmuxTree(windows=[w])

        surfaces = tree.all_surfaces()
        assert len(surfaces) == 3
        assert {s.title for s in surfaces} == {"bash", "vim", "Chrome"}

    def test_find_surface(self):
        s = Surface(ref=SurfaceRef("s:42"), title="target", type=SurfaceType.TERMINAL)
        p = Pane(ref="pane:1", surfaces=[s])
        ws = Workspace(ref="ws:1", title="main", panes=[p])
        w = Window(ref="win:1", workspaces=[ws])
        tree = CmuxTree(windows=[w])

        found = tree.find_surface(SurfaceRef("s:42"))
        assert found is not None
        assert found.title == "target"

        not_found = tree.find_surface(SurfaceRef("s:999"))
        assert not_found is None

    def test_deep_hierarchy(self):
        """Test 2 windows, 3 workspaces, 4 panes, 5 surfaces."""
        surfaces = []
        panes = []
        for i in range(5):
            s = Surface(ref=SurfaceRef(f"s:{i}"), title=f"term:{i}", type=SurfaceType.TERMINAL)
            surfaces.append(s)
            panes.append(Pane(ref=f"pane:{i}", surfaces=[s]))

        ws1 = Workspace(ref="ws:1", title="w1", panes=panes[:2])
        ws2 = Workspace(ref="ws:2", title="w2", panes=panes[2:4])
        ws3 = Workspace(ref="ws:3", title="w3", panes=[panes[4]])
        w1 = Window(ref="win:1", workspaces=[ws1, ws2])
        w2 = Window(ref="win:2", workspaces=[ws3])
        tree = CmuxTree(windows=[w1, w2])

        assert len(tree.all_surfaces()) == 5
        assert len(tree.windows) == 2


class TestScreenSnapshot:
    def test_creation(self):
        snap = ScreenSnapshot(ref=SurfaceRef("s:1"), content="hello\nworld", lines=2)
        assert snap.content == "hello\nworld"
        assert snap.scrollback is False

    def test_with_metadata(self):
        snap = ScreenSnapshot(
            ref=SurfaceRef("s:1"), content="data", lines=1,
            metadata={"agent": "claude", "task": "debug"}
        )
        assert snap.metadata["agent"] == "claude"


class TestEvents:
    def test_tree_updated(self):
        tree = CmuxTree()
        event = TreeUpdated(tree=tree)
        assert event.tree is tree

    def test_surface_screen_updated(self):
        snap = ScreenSnapshot(ref=SurfaceRef("s:1"), content="out", lines=1)
        event = SurfaceScreenUpdated(ref=SurfaceRef("s:1"), snapshot=snap)
        assert event.snapshot.content == "out"

    def test_synthesis_ready(self):
        result = SynthesisResult(
            per_surface=[], global_focus_list=["fix bug"], raw_text="analysis", timestamp=1.0
        )
        event = SynthesisReady(result=result)
        assert event.result.raw_text == "analysis"


class TestSynthesisModels:
    def test_per_surface_state(self):
        state = PerSurfaceState(
            ref=SurfaceRef("s:1"), agent_type="claude-code",
            current_task="fix parser", state="working",
            last_output_summary="running tests", priority=3
        )
        assert state.state == "working"
        assert state.priority == 3

    def test_synthesis_result(self):
        result = SynthesisResult(
            per_surface=[
                PerSurfaceState(SurfaceRef("s:1"), "claude", "debug", "working", "compiling", 2),
            ],
            global_focus_list=["attach to s:1", "check tests"],
            raw_text="full analysis here",
            timestamp=1234567890.0,
        )
        assert len(result.per_surface) == 1
        assert len(result.global_focus_list) == 2

    def test_surface_context(self):
        s = Surface(ref=SurfaceRef("s:1"), title="bash", type=SurfaceType.TERMINAL)
        snap = ScreenSnapshot(ref=SurfaceRef("s:1"), content="output", lines=1)
        ctx = SurfaceContext(surface=s, snapshot=snap, inferred_agent="claude-code")
        assert ctx.inferred_agent == "claude-code"

    def test_synthesis_context(self):
        s = Surface(ref=SurfaceRef("s:1"), title="bash", type=SurfaceType.TERMINAL)
        snap = ScreenSnapshot(ref=SurfaceRef("s:1"), content="out", lines=1)
        sc = SynthesisContext(
            surfaces=[SurfaceContext(surface=s, snapshot=snap)],
            global_notes="GSD phase 3"
        )
        assert sc.global_notes == "GSD phase 3"
        assert len(sc.surfaces) == 1
