import pytest
from unittest.mock import MagicMock, patch
from aishorts.modules.latex.latex_providers import (
    Matplotlib,
    RealLatex,
    Resolution,
    LatexResult,
)
from aishorts.modules.script.script import Reel, Block, LatexMedia, Trigger


@pytest.fixture
def resolution():
    return Resolution(width=100, height=100)


class TestMatplotlib:
    @patch("aishorts.modules.latex.latex_providers.Figure")
    @patch("aishorts.modules.latex.latex_providers.FigureCanvasAgg")
    def test_render_single(self, mock_canvas, mock_figure, resolution):
        provider = Matplotlib()

        # Setup mocks
        mock_fig_instance = mock_figure.return_value
        mock_ax = MagicMock()
        mock_fig_instance.add_axes.return_value = mock_ax

        # Mock text bbox to exit loop immediately
        mock_txt = MagicMock()
        mock_bbox = MagicMock()
        mock_bbox.width = 50
        mock_bbox.height = 50
        mock_txt.get_window_extent.return_value = mock_bbox
        mock_ax.text.return_value = mock_txt

        result = provider.render_single(1, "E=mc^2", resolution)

        assert isinstance(result, LatexResult)
        assert result.alt == "E=mc^2"
        mock_fig_instance.savefig.assert_called_once()

    def test_get_reel_images(self, resolution):
        provider = Matplotlib()
        trigger = Trigger(start_word_index=0, end_word_index=1)
        reel = Reel(
            title="T",
            description="D",
            blocks=[
                Block(
                    type="dialogue",
                    avatar="a",
                    text="t",
                    media=LatexMedia(type="latex", code="code1", trigger=trigger),
                ),
                Block(type="dialogue", avatar="a", text="t", media=None),
            ],
        )

        with patch.object(provider, "render_single") as mock_render:
            mock_render.return_value = LatexResult(media=MagicMock(), alt="code1")
            results = provider.get_reel_images(reel, resolution)

            assert len(results) == 1
            mock_render.assert_called_once()


class TestRealLatex:
    @patch("aishorts.modules.latex.latex_providers.subprocess.run")
    @patch("aishorts.modules.latex.latex_providers.Image")
    @patch("builtins.open", new_callable=MagicMock)
    def test_render_single_success(self, mock_open, mock_image, mock_run, resolution):
        provider = RealLatex()

        # Mock subprocess success
        mock_run.return_value.returncode = 0

        # Mock Image
        mock_img_instance = MagicMock()
        mock_img_instance.size = (50, 50)
        mock_img_instance.convert.return_value = mock_img_instance
        mock_image.open.return_value = mock_img_instance
        mock_image.new.return_value = MagicMock()

        # Mock os.path.exists and os.remove
        with patch("os.path.exists", return_value=True), patch("os.remove"):
            result = provider._render_single(1, "code", resolution)

        assert isinstance(result, LatexResult)
        assert result.alt == "code"
        # Check subprocess calls (pdflatex, pdftocairo x2)
        assert mock_run.call_count >= 3

    @patch("aishorts.modules.latex.latex_providers.subprocess.run")
    def test_render_single_failure(self, mock_run, resolution):
        provider = RealLatex()
        mock_run.return_value.returncode = 1  # Failure

        with pytest.raises(RuntimeError):
            with patch("builtins.open", new_callable=MagicMock):
                provider._render_single(1, "code", resolution)
