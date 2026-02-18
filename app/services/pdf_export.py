from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas import MediaPlanResult


class PDFExportService:
    def generate(self, media_plan: MediaPlanResult) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
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

        story.append(Spacer(1, 24))
        story.append(Paragraph("Данные получены через Wordstat API", styles["Italic"]))

        doc.build(story)
        return buffer.getvalue()
