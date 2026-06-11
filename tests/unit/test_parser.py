"""Unit tests for cmux tree parser."""
import pytest
import json
from cmux_remote_tui.domain.parser import parse_cmux_tree, parse_from_json_string
from cmux_remote_tui.domain.models import CmuxTree, SurfaceType, SurfaceRef


class TestParseCmuxTree:
    def test_empty(self):
        tree = parse_cmux_tree({})
        assert tree.windows == []
        assert tree.active_surface is None
        assert len(tree.all_surfaces()) == 0

    def test_empty_windows(self):
        tree = parse_cmux_tree({"windows": []})
        assert tree.windows == []

    def test_single_terminal_surface(self):
        raw = {
            "windows": [{
                "ref": "win:1",
                "workspaces": [{
                    "ref": "ws:1",
                    "title": "main",
                    "active": True,
                    "panes": [{
                        "ref": "pane:1",
                        "surfaces": [{
                            "ref": "surface:42",
                            "title": "bash",
                            "type": "terminal",
                            "tty": "/dev/ttys001",
                        }]
                    }]
                }]
            }],
            "active": "surface:42"
        }
        tree = parse_cmux_tree(raw)
        assert len(tree.windows) == 1
        assert tree.active_surface == SurfaceRef("surface:42")

        surfaces = tree.all_surfaces()
        assert len(surfaces) == 1
        assert surfaces[0].title == "bash"
        assert surfaces[0].type == SurfaceType.TERMINAL
        assert surfaces[0].tty == "/dev/ttys001"

    def test_browser_surface(self):
        raw = {
            "windows": [{
                "ref": "win:1",
                "workspaces": [{
                    "ref": "ws:1",
                    "title": "browsers",
                    "panes": [{
                        "ref": "pane:1",
                        "surfaces": [{
                            "ref": "surface:99",
                            "title": "Chrome",
                            "type": "browser",
                            "url": "https://example.com",
                        }]
                    }]
                }]
            }]
        }
        tree = parse_cmux_tree(raw)
        surfaces = tree.all_surfaces()
        assert len(surfaces) == 1
        assert surfaces[0].type == SurfaceType.BROWSER
        assert surfaces[0].url == "https://example.com"

    def test_mixed_surfaces(self):
        raw = {
            "windows": [{
                "ref": "win:1",
                "workspaces": [{
                    "ref": "ws:1",
                    "title": "dev",
                    "panes": [{
                        "ref": "pane:1",
                        "surfaces": [
                            {"ref": "s:1", "title": "bash", "type": "terminal"},
                            {"ref": "s:2", "title": "vim", "type": "terminal"},
                            {"ref": "s:3", "title": "firefox", "type": "browser", "url": "https://x.com"},
                        ]
                    }]
                }]
            }]
        }
        tree = parse_cmux_tree(raw)
        surfaces = tree.all_surfaces()
        assert len(surfaces) == 3
        assert sum(1 for s in surfaces if s.is_terminal) == 2
        assert sum(1 for s in surfaces if s.is_browser) == 1

    def test_missing_optional_fields(self):
        raw = {
            "windows": [{
                "ref": "win:1",
                "workspaces": [{
                    "ref": "ws:1",
                    "title": "",
                    "panes": [{
                        "ref": "pane:1",
                        "surfaces": [{
                            "ref": "s:1",
                            "title": "x",
                            "type": "terminal",
                        }]
                    }]
                }]
            }]
        }
        tree = parse_cmux_tree(raw)
        s = tree.all_surfaces()[0]
        assert s.tty is None
        assert s.url is None
        assert s.selected is False
        assert s.active is False

    def test_missing_ref_defaults_to_empty_string(self):
        raw = {
            "windows": [{
                "ref": "win:1",
                "workspaces": [{
                    "ref": "ws:1",
                    "title": "t",
                    "panes": [{
                        "ref": "pane:1",
                        "surfaces": [{"title": "x", "type": "terminal"}]
                    }]
                }]
            }]
        }
        tree = parse_cmux_tree(raw)
        s = tree.all_surfaces()[0]
        assert s.ref == SurfaceRef("")

    def test_unknown_surface_type_raises(self):
        """Unknown surface type raises ValueError (strict enum)."""
        raw = {
            "windows": [{
                "ref": "win:1",
                "workspaces": [{
                    "ref": "ws:1",
                    "title": "t",
                    "panes": [{
                        "ref": "pane:1",
                        "surfaces": [{"ref": "s:1", "title": "x", "type": "unknown_type"}]
                    }]
                }]
            }]
        }
        with pytest.raises(ValueError):
            parse_cmux_tree(raw)

    def test_multiple_windows_and_workspaces(self):
        raw = {
            "windows": [
                {
                    "ref": "win:1",
                    "workspaces": [
                        {"ref": "ws:1", "title": "a", "panes": [{"ref": "p:1", "surfaces": [{"ref": "s:1", "title": "t1", "type": "terminal"}]}]},
                        {"ref": "ws:2", "title": "b", "panes": [{"ref": "p:2", "surfaces": [{"ref": "s:2", "title": "t2", "type": "terminal"}]}]},
                    ]
                },
                {
                    "ref": "win:2",
                    "workspaces": [
                        {"ref": "ws:3", "title": "c", "panes": [{"ref": "p:3", "surfaces": [{"ref": "s:3", "title": "t3", "type": "terminal"}]}]},
                    ]
                }
            ]
        }
        tree = parse_cmux_tree(raw)
        assert len(tree.windows) == 2
        assert len(tree.all_surfaces()) == 3

    def test_active_surface_none(self):
        raw = {"windows": [], "active": None}
        tree = parse_cmux_tree(raw)
        assert tree.active_surface is None

    def test_active_surface_missing(self):
        raw = {"windows": []}
        tree = parse_cmux_tree(raw)
        assert tree.active_surface is None


class TestParseFromJsonString:
    def test_valid_json(self):
        raw = json.dumps({
            "windows": [{
                "ref": "win:1",
                "workspaces": [{
                    "ref": "ws:1",
                    "title": "main",
                    "panes": [{
                        "ref": "pane:1",
                        "surfaces": [{"ref": "s:1", "title": "bash", "type": "terminal"}]
                    }]
                }]
            }]
        })
        tree = parse_from_json_string(raw)
        assert len(tree.all_surfaces()) == 1

    def test_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            parse_from_json_string("not json")
