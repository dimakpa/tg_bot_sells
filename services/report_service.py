from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Iterable, Dict, Any, List, Tuple
import re
import textwrap

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from storage.models import Transaction, Category, TransactionKind
from loguru import logger

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


class ReportService:
	def __init__(self, session: AsyncSession, export_dir: str = "exports") -> None:
		self.session = session
		self.export_dir = Path(export_dir)
		self.export_dir.mkdir(parents=True, exist_ok=True)

	@staticmethod
	def _sanitize(text: Optional[str]) -> str:
		"""Удаляет эмодзи и символы вне BMP, чтобы избежать квадратиков в PDF/PNG."""
		if not text:
			return ""
		return re.sub(r"[\U00010000-\U0010FFFF]", "", text)

	@staticmethod
	def _wrap(text: str, width: int = 18) -> str:
		"""Переносит длинные строки в тексте для таблицы."""
		if not text:
			return ""
		return "\n".join(textwrap.wrap(text, width=width))

	async def _load_category_map(self) -> Dict[int, str]:
		result = await self.session.execute(select(Category.id, Category.name))
		rows = result.all()
		return {row.id: row.name for row in rows}

	async def fetch_transactions(
		self,
		user_id: int,
		kind: TransactionKind,
		start_date: Optional[datetime] = None,
		end_date: Optional[datetime] = None,
		category_ids: Optional[Iterable[int]] = None,
		subcategory_ids: Optional[Iterable[int]] = None,
		amount_min: Optional[Decimal] = None,
		amount_max: Optional[Decimal] = None,
		comment_query: Optional[str] = None,
		limit: Optional[int] = None,
	) -> List[Transaction]:
		filters = [
			Transaction.user_id == user_id,
			Transaction.kind == kind,
		]

		if start_date:
			filters.append(Transaction.effective_at >= start_date)
		if end_date:
			filters.append(Transaction.effective_at <= end_date)
		if category_ids:
			filters.append(Transaction.category_id.in_(list(category_ids)))
		if subcategory_ids:
			filters.append(Transaction.subcategory_id.in_(list(subcategory_ids)))
		if amount_min is not None:
			filters.append(Transaction.amount >= amount_min)
		if amount_max is not None:
			filters.append(Transaction.amount <= amount_max)
		if comment_query:
			filters.append(Transaction.comment.ilike(f"%{comment_query}%"))

		query = (
			select(Transaction)
			.where(and_(*filters))
			.order_by(Transaction.effective_at.asc())
		)
		if limit:
			query = query.limit(limit)
		result = await self.session.execute(query)
		return result.scalars().all()

	@staticmethod
	def _build_dataframe(transactions: List[Transaction], category_map: Dict[int, str]) -> pd.DataFrame:
		records: List[Dict[str, Any]] = []
		for t in transactions:
			records.append({
				"Дата": t.effective_at.strftime("%Y-%m-%d %H:%M"),
				"Категория": category_map.get(t.category_id, str(t.category_id)),
				"Подкатегория": category_map.get(t.subcategory_id, "-") if t.subcategory_id else "-",
				"Сумма": float(t.amount),
				"Валюта": t.currency,
				"Комментарий": ReportService._sanitize(t.comment),
			})
		return pd.DataFrame.from_records(records) if records else pd.DataFrame(columns=["Дата","Категория","Подкатегория","Сумма","Валюта","Комментарий"]) 

	@staticmethod
	def _ensure_unicode_font() -> str | None:
		font_path = Path("assets/fonts/DejaVuSans.ttf")
		if font_path.exists():
			font_name = "DejaVuSans"
			try:
				pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
				return font_name
			except Exception as e:
				logger.warning(f"Не удалось зарегистрировать шрифт {font_path}: {e}")
		return None

	@staticmethod
	def _write_excel(df: pd.DataFrame, kind: TransactionKind, summary: Dict[str, Any], out_path: Path, aggregate_df: Optional[pd.DataFrame] = None, aggregate_title: Optional[str] = None, extra_sheets: Optional[Dict[str, pd.DataFrame]] = None) -> None:
		with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
			df.to_excel(writer, index=False, sheet_name="data")
			pd.DataFrame({
				"metric": ["kind", "total", "count"],
				"value": [summary["kind"], summary["total"], summary["count"]],
			}).to_excel(writer, index=False, sheet_name="summary")
			pd.DataFrame({
				"generated_at": [datetime.utcnow().isoformat(timespec="seconds")],
				"type": [kind.value],
			}).to_excel(writer, index=False, sheet_name="meta")
			if aggregate_df is not None:
				name = aggregate_title or "aggregate"
				aggregate_df.to_excel(writer, index=False, sheet_name=name)
			if extra_sheets:
				for name, sdf in extra_sheets.items():
					# Excel sheet name limit 31
					writer_sheet = (name[:28] + '...') if len(name) > 31 else name
					sdf.to_excel(writer, index=False, sheet_name=writer_sheet)

	def _render_table_on_axis(self, ax: plt.Axes, table_df: pd.DataFrame, title: Optional[str] = None) -> None:
		"""Рисует таблицу на оси matplotlib с украшенными ячейками."""
		ax.axis('off')
		if title:
			ax.set_title(self._sanitize(title), fontsize=10, pad=8)
		# Подготовка данных: перенос долгих текстов
		disp = table_df.copy()
		for col in disp.columns:
			if disp[col].dtype == object:
				disp[col] = disp[col].map(lambda x: self._wrap(str(x)) if isinstance(x, str) else x)
		if not disp.empty and 'Сумма' in disp.columns:
			disp['Сумма'] = disp['Сумма'].map(lambda x: f"{x:,.2f}".replace(',', ' ').replace('.', ','))
		# Создаём таблицу
		tab = ax.table(cellText=disp.values, colLabels=list(disp.columns), loc='center', cellLoc='left', colLoc='center')
		tab.auto_set_font_size(False)
		tab.set_fontsize(8)
		tab.scale(1.0, 1.25)
		# Стили: хедер + зебра + границы + выравнивание
		header_bg = '#f0f4ff'
		odd_bg = '#fafafa'
		for (r, c), cell in tab.get_celld().items():
			cell.set_edgecolor('#cccccc')
			cell.set_linewidth(0.6)
			cell.get_text().set_color('#222222')
			if r == 0:
				cell.set_facecolor(header_bg)
				cell.get_text().set_weight('bold')
				cell.get_text().set_ha('center')
			else:
				if r % 2 == 1:
					cell.set_facecolor(odd_bg)
				# Выравнивание чисел
				if disp.columns[c] == 'Сумма':
					cell.get_text().set_ha('right')
				elif disp.columns[c] == 'Дата':
					cell.get_text().set_ha('center')

	def _write_png(self, table_df: pd.DataFrame, kind: TransactionKind, summary: Dict[str, Any], out_path: Path, title_suffix: str = "") -> None:
		"""Рисует единую таблицу на PNG."""
		plt.rcParams['font.family'] = 'DejaVu Sans'
		plt.figure(figsize=(11.7, 8.3), dpi=150)  # A4 ландшафт
		base_title = self._sanitize(f"Отчёт: { 'Траты' if kind == TransactionKind.EXPENSE else 'Продажи' } — сумма {summary['total']:.2f}, операций {summary['count']}")
		title = base_title + (f" — {title_suffix}" if title_suffix else "")
		plt.title(title)
		ax = plt.gca()
		self._render_table_on_axis(ax, table_df)
		plt.tight_layout()
		plt.savefig(out_path, bbox_inches='tight')
		plt.close()

	def _write_png_sections(self, png_tables: List[Tuple[str, pd.DataFrame]], kind: TransactionKind, summary: Dict[str, Any], out_path: Path) -> None:
		"""Рисует ВСЕ таблицы категорий на одном PNG, одна таблица на строку."""
		plt.rcParams['font.family'] = 'DejaVu Sans'
		n = len(png_tables)
		if n == 0:
			# пустой
			plt.figure(figsize=(11.7, 4), dpi=150)
			title = self._sanitize(f"Отчёт: {'Траты' if kind == TransactionKind.EXPENSE else 'Продажи'} — нет данных")
			plt.title(title)
			plt.axis('off')
			plt.savefig(out_path, bbox_inches='tight')
			plt.close()
			return
		# ограничим, чтобы не было слишком огромного файла
		max_tables = min(n, 12)
		fig_height = 2 + max_tables * 2.8  # эмпирически
		fig, axes = plt.subplots(nrows=max_tables, ncols=1, figsize=(11.7, fig_height), dpi=150)
		if max_tables == 1:
			axes = [axes]
		suptitle = self._sanitize(f"Отчёт: {'Траты' if kind == TransactionKind.EXPENSE else 'Продажи'} — сумма {summary['total']:.2f}, операций {summary['count']}")
		fig.suptitle(suptitle, fontsize=12)
		for i, (cat_name, df) in enumerate(png_tables[:max_tables]):
			ax = axes[i]
			self._render_table_on_axis(ax, df, title=cat_name)
		fig.tight_layout(rect=[0, 0, 1, 0.96])
		fig.savefig(out_path, bbox_inches='tight')
		plt.close(fig)

	@staticmethod
	def _aggregate_df(df: pd.DataFrame, mode: Optional[str]) -> Tuple[pd.DataFrame, Optional[str]]:
		if df.empty or not mode or mode == 'detail':
			return df, None
		if mode == 'by_category':
			agg = (
				df.groupby(['Категория'], as_index=False)
				.agg(Количество=('Сумма', 'count'), Сумма=('Сумма', 'sum'))
				.sort_values('Сумма', ascending=False)
			)
			return agg, 'по категориям'
		if mode == 'by_subcategory':
			agg = df.groupby(['Категория','Подкатегория'], as_index=False)['Сумма'].sum().sort_values('Сумма', ascending=False)
			return agg, 'по подкатегориям'
		if mode == 'overall':
			total = float(df['Сумма'].sum())
			count = int(len(df))
			agg = pd.DataFrame({
				"Показатель": ["Сумма", "Число операций"],
				"Значение": [total, count]
			})
			return agg, 'итого'
		return df, None

	def _build_category_sections(self, df: pd.DataFrame) -> Tuple[Dict[str, pd.DataFrame], List[Tuple[str, pd.DataFrame]]]:
		"""Готовит листы Excel и таблицы для PNG: по каждой категории агрегируем подкатегории"""
		sheets: Dict[str, pd.DataFrame] = {}
		png_tables: List[Tuple[str, pd.DataFrame]] = []
		if df.empty:
			return sheets, png_tables
		cats = df.groupby('Категория', as_index=False)['Сумма'].sum().sort_values('Сумма', ascending=False)
		for _, row in cats.iterrows():
			cat_name = str(row['Категория'])
			sub = df[df['Категория'] == cat_name].groupby('Подкатегория', as_index=False)['Сумма'].sum().sort_values('Сумма', ascending=False)
			sub.columns = ['Подкатегория', 'Сумма']
			sheets[f"{cat_name}"] = sub
			png_tables.append((cat_name, sub))
		return sheets, png_tables

	def _write_pdf(self, df: pd.DataFrame, kind: TransactionKind, summary: Dict[str, Any], out_path: Path) -> None:
		font_name = self._ensure_unicode_font()
		doc = SimpleDocTemplate(str(out_path), pagesize=A4, rightMargin=24, leftMargin=24, topMargin=24, bottomMargin=24)
		styles = getSampleStyleSheet()
		if font_name:
			styles['Normal'].fontName = font_name
			styles['Heading1'].fontName = font_name
		story: List[Any] = []

		title = Paragraph(ReportService._sanitize(f"Отчёт: { 'Траты' if kind == TransactionKind.EXPENSE else 'Продажи' }"), styles['Heading1'])
		story.append(title)
		story.append(Spacer(1, 12))
		meta = Paragraph(ReportService._sanitize(f"Сумма: {summary['total']:.2f} ({summary['count']} операций)"), styles['Normal'])
		story.append(meta)
		story.append(Spacer(1, 12))

		data = [list(df.columns)] + df.head(40).values.tolist()
		table = Table(data, repeatRows=1)
		style_cmds = [
			('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
			('GRID', (0,0), (-1,-1), 0.25, colors.grey),
			('ALIGN', (3,1), (3,-1), 'RIGHT'),
			('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
		]
		if font_name:
			style_cmds.append(('FONT', (0,0), (-1,-1), font_name, 10))
		table.setStyle(TableStyle(style_cmds))
		story.append(table)
		doc.build(story)

	async def build_report(
		self,
		user_id: int,
		kind: TransactionKind,
		start_date: Optional[datetime] = None,
		end_date: Optional[datetime] = None,
		category_ids: Optional[Iterable[int]] = None,
		subcategory_ids: Optional[Iterable[int]] = None,
		amount_min: Optional[Decimal] = None,
		amount_max: Optional[Decimal] = None,
		comment_query: Optional[str] = None,
		aggregation: Optional[str] = None,
	) -> Tuple[Path, List[Path], Dict[str, Any]]:
		if not end_date:
			end_date = datetime.utcnow()
		if not start_date:
			start_date = end_date - timedelta(days=30)

		transactions = await self.fetch_transactions(
			user_id=user_id,
			kind=kind,
			start_date=start_date,
			end_date=end_date,
			category_ids=category_ids,
			subcategory_ids=subcategory_ids,
			amount_min=amount_min,
			amount_max=amount_max,
			comment_query=comment_query,
			limit=None,
		)

		category_map = await self._load_category_map()
		df = self._build_dataframe(transactions, category_map)
		total = float(df["Сумма"].sum()) if not df.empty else 0.0
		count = int(len(df))
		summary = {"kind": kind.value, "total": total, "count": count}

		timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
		base = self.export_dir / f"report_{kind.value}_{user_id}_{timestamp}"
		xlsx_path = base.with_suffix('.xlsx')
		png_paths: List[Path] = []

		if aggregation == 'by_category_sections' and kind == TransactionKind.EXPENSE:
			# Excel: по категориям листы (суммы по подкатегориям)
			extra_sheets, png_tables = self._build_category_sections(df)
			self._write_excel(df, kind, summary, xlsx_path, extra_sheets=extra_sheets)
			# единый PNG
			png_path = base.with_suffix('.png')
			self._write_png_sections(png_tables, kind, summary, png_path)
			png_paths.append(png_path)
		else:
			# обычные режимы
			agg_df, agg_title = self._aggregate_df(df, aggregation)
			self._write_excel(df, kind, summary, xlsx_path, aggregate_df=(agg_df if agg_title else None), aggregate_title=("aggregate_" + agg_title if agg_title else None))
			display_df = agg_df if agg_title else df
			title_suffix = agg_title or ""
			png_path = base.with_suffix('.png')
			self._write_png(display_df, kind, summary, png_path, title_suffix=title_suffix)
			png_paths.append(png_path)

		logger.info(f"Сформирован отчёт: {xlsx_path.name}, {[p.name for p in png_paths]}")
		return xlsx_path, png_paths, summary 