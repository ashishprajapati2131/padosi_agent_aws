"""
Bulk Product CSV Import Service.
Handles parsing, schema validation, SKU deduplication, and error logging.
"""
import csv
import io
from decimal import Decimal
from datetime import datetime
from typing import Tuple, List, Dict
from django.utils.text import slugify
from django.db import transaction
from apps.wholesale.models.import_job import BulkImportJob, BulkImportError
from apps.wholesale.models.product import WholesaleProduct
from apps.wholesale.models.category import ProductCategory
from apps.wholesale.models.profile import WholesalerProfile

class BulkImportService:
    """Processes bulk CSV product uploads."""

    CSV_HEADERS = [
        'title',
        'sku',
        'category_name',
        'brand',
        'base_price',
        'moq',
        'unit_of_measure',
        'stock_quantity',
        'short_description',
        'description',
    ]

    @staticmethod
    def generate_sample_csv() -> str:
        """Generates downloadable sample CSV template with example row."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(BulkImportService.CSV_HEADERS)
        writer.writerow([
            'Policy Presentation Leatherette Folders (Navy Gold)',
            'KIT-FOLDER-01',
            'Office & Stationery Supplies',
            'Padosi Supplies',
            '180.00',
            '50',
            'Piece',
            '500',
            'Premium gold-embossed leatherette certificate & policy folder with card slot',
            'Executive file folder with dual transparent internal leaves and metallic clip.',
        ])
        writer.writerow([
            'Executive Metal Rollerball Pen with Custom Agency Engraving',
            'PEN-EXEC-02',
            'Marketing & Promotional Merchandise',
            'SignaCraft',
            '95.00',
            '100',
            'Piece',
            '2000',
            'Heavyweight matte black metal pen with laser engraving capability',
            'Smooth German blue ink refill, weighted body, delivered in gift box sleeve.',
        ])
        return output.getvalue()

    @staticmethod
    def process_import_job(job: BulkImportJob) -> BulkImportJob:
        """Parses CSV and creates draft products, collecting row errors."""
        job.status = 'PROCESSING'
        job.save(update_fields=['status'])

        wholesaler = job.wholesaler
        success_count = 0
        failed_count = 0

        try:
            file_content = job.file.read().decode('utf-8', errors='ignore')
            reader = csv.DictReader(io.StringIO(file_content))
            
            # Verify required columns
            if not reader.fieldnames:
                raise ValueError("CSV file is empty or corrupted.")
            
            missing_cols = [col for col in ['title', 'sku', 'base_price', 'moq'] if col not in reader.fieldnames]
            if missing_cols:
                raise ValueError(f"Missing required columns: {', '.join(missing_cols)}")

            row_num = 1
            for row in reader:
                row_num += 1
                row_errors = []

                from apps.admin_panel.services.spreadsheet_safety import safe_cell

                title = safe_cell((row.get('title') or '').strip())
                sku = safe_cell((row.get('sku') or '').strip())
                cat_name = (row.get('category_name') or '').strip()
                base_price_str = (row.get('base_price') or '').strip()
                moq_str = (row.get('moq') or '1').strip()
                unit = (row.get('unit_of_measure') or 'Piece').strip()
                stock_str = (row.get('stock_quantity') or '0').strip()
                brand = safe_cell((row.get('brand') or '').strip())
                raw_short = (row.get('short_description') or title)[:490].strip()
                short_desc = safe_cell(raw_short)
                raw_desc = (row.get('description') or title).strip()
                desc = safe_cell(raw_desc)

                if not title:
                    row_errors.append("Title cannot be empty.")
                if not sku:
                    row_errors.append("SKU is required.")
                elif WholesaleProduct.objects.filter(wholesaler=wholesaler, sku=sku).exists():
                    row_errors.append(f"SKU '{sku}' already exists in your inventory.")

                try:
                    base_price = Decimal(base_price_str)
                    if base_price <= 0:
                        row_errors.append("Base price must be greater than 0.")
                except Exception:
                    row_errors.append(f"Invalid base price: '{base_price_str}'.")

                try:
                    moq = int(moq_str)
                    if moq < 1:
                        row_errors.append("MOQ must be at least 1.")
                except Exception:
                    row_errors.append(f"Invalid MOQ: '{moq_str}'.")

                try:
                    stock = max(0, int(stock_str))
                except Exception:
                    stock = 0

                # Resolve or assign category
                category = None
                if cat_name:
                    category = ProductCategory.objects.filter(name__iexact=cat_name).first()
                if not category:
                    category = ProductCategory.objects.first()
                if not category:
                    category = ProductCategory.objects.create(name='Agent Office Supplies', slug='agent-office-supplies')

                if row_errors:
                    failed_count += 1
                    for err in row_errors:
                        BulkImportError.objects.create(
                            job=job,
                            row_number=row_num,
                            sku=sku,
                            error_message=err
                        )
                    continue

                # Create draft product
                try:
                    with transaction.atomic():
                        WholesaleProduct.objects.create(
                            wholesaler=wholesaler,
                            category=category,
                            title=title,
                            sku=sku,
                            brand=brand or None,
                            base_price=base_price,
                            moq=moq,
                            unit_of_measure=unit,
                            stock_quantity=stock,
                            short_description=short_desc,
                            description=desc,
                            approval_status='DRAFT'
                        )
                        success_count += 1
                except Exception as ex:
                    failed_count += 1
                    BulkImportError.objects.create(
                        job=job,
                        row_number=row_num,
                        sku=sku,
                        error_message=str(ex)
                    )

            job.total_rows = success_count + failed_count
            job.success_count = success_count
            job.failed_count = failed_count
            job.status = 'COMPLETED' if failed_count == 0 else ('PARTIAL' if success_count > 0 else 'FAILED')
            job.completed_at = datetime.now()
            job.summary_message = f"Successfully imported {success_count} products as drafts. {failed_count} rows failed."
            job.save()

        except Exception as e:
            job.status = 'FAILED'
            job.summary_message = f"Import failed: {str(e)}"
            job.completed_at = datetime.now()
            job.save()

        return job
