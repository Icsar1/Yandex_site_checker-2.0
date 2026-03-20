from __future__ import annotations

from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas import MediaPlanResult


class PDFExportService:
    _FONT_NAME = "DejaVuSans"
    _FONT_NAME_BOLD = "DejaVuSans-Bold"

    def __init__(self) -> None:
        self._register_fonts()

    def generate(self, media_plan: MediaPlanResult) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = self._build_styles()
        story = []

        story.append(Paragraph("Медиаплан Яндекс Wordstat", styles["Title"]))
        story.append(Spacer(1, 12))

        data = media_plan.input_data
        story.append(Paragraph(f"Ниша: {data.niche}", styles["Normal"]))
        story.append(Paragraph(f"Регион: {data.region}", styles["Normal"]))
        story.append(Paragraph(f"Бюджет: {data.monthly_budget if data.monthly_budget else '-'}", styles["Normal"]))
        story.append(Paragraph(f"Цель: {data.campaign_goal if data.campaign_goal else '-'}", styles["Normal"]))
        story.append(Paragraph(f"Дата: {media_plan.created_at.strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
        story.append(Spacer(1, 12))

        table_rows = [["Фраза", "Частотность", "Тип соответствия", "Приоритет"]]
        for item in media_plan.keywords:
            table_rows.append([item.phrase, str(item.frequency), item.match_type or "-", item.priority])

        table = Table(table_rows, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTNAME", (0, 0), (-1, 0), self._FONT_NAME_BOLD),
                    ("FONTNAME", (0, 1), (-1, -1), self._FONT_NAME),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 12))

        summary = media_plan.summary
        story.append(Paragraph(f"Всего ключей: {summary.total_keywords}", styles["Normal"]))
        story.append(Paragraph(f"Суммарная частотность: {summary.total_frequency}", styles["Normal"]))
        story.append(Paragraph(f"Средняя частотность: {summary.avg_frequency}", styles["Normal"]))
        if summary.budget_distribution:
            story.append(
                Paragraph(
                    "Распределение бюджета: "
                    f"high={summary.budget_distribution['high']}, "
                    f"medium={summary.budget_distribution['medium']}, "
                    f"low={summary.budget_distribution['low']}",
                    styles["Normal"],
                )
            )
 codex/create-web-app-for-media-plan-using-yandex-api-f1le2c

        story.append(Spacer(1, 24))
        story.append(Paragraph("Данные получены через Wordstat API", styles["Italic"]))

=======
        story.append(Spacer(1, 24))
        story.append(Paragraph("Данные получены через Wordstat API", styles["Italic"]))
 main
        doc.build(story)
        return buffer.getvalue()

    def _build_styles(self) -> dict[str, ParagraphStyle]:
        sample_styles = getSampleStyleSheet()
        return {
            "Title": ParagraphStyle(
                "TitleCyr",
                parent=sample_styles["Title"],
                fontName=self._FONT_NAME_BOLD,
            ),
            "Normal": ParagraphStyle(
                "NormalCyr",
                parent=sample_styles["Normal"],
                fontName=self._FONT_NAME,
            ),
            "Italic": ParagraphStyle(
                "ItalicCyr",
                parent=sample_styles["Italic"],
                fontName=self._FONT_NAME,
            ),
        }

    @classmethod
    def _register_fonts(cls) -> None:
        if cls._FONT_NAME in pdfmetrics.getRegisteredFontNames():
            return
 codex/create-web-app-for-media-plan-using-yandex-api-f1le2c

=======
 main
        regular_path, bold_path = cls._resolve_font_paths()
        pdfmetrics.registerFont(TTFont(cls._FONT_NAME, str(regular_path)))
        pdfmetrics.registerFont(TTFont(cls._FONT_NAME_BOLD, str(bold_path)))

    @staticmethod
    def _resolve_font_paths() -> tuple[Path, Path]:
        candidates = [
            (
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            ),
            (
                Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
                Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
            ),
        ]
 codex/create-web-app-for-media-plan-using-yandex-api-f1le2c

        for regular, bold in candidates:
            if regular.exists() and bold.exists():
                return regular, bold

=======
        for regular, bold in candidates:
            if regular.exists() and bold.exists():
                return regular, bold
 main
        raise FileNotFoundError(
            "Не найден шрифт DejaVuSans для генерации PDF с кириллицей. "
            "Установите пакет шрифтов dejavu-fonts."
        )
