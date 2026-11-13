"""Audit phase 4: INS7 (bad variant payload changes nothing), INS10 (toggle is
POST-only), INS12 (bulk import caps, case-insensitive .csv, unknown category)."""

import json
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.wholesale.forms.product_forms import ProductWizardForm
from apps.wholesale.models.import_job import BulkImportJob
from apps.wholesale.models.product import ProductVariant, WholesaleProduct
from apps.wholesale.services.bulk_import_service import BulkImportService
from apps.wholesale.test_security import WholesaleSecurityBase

HEADER = "title,sku,category_name,base_price,moq\n"


class WholesalePhase4Tests(WholesaleSecurityBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.variant = ProductVariant.objects.create(
            product=self.product, name="Blue", sku="V-BLUE", stock_quantity=3
        )

    def _edit(self, variants_json):
        form = ProductWizardForm(instance=self.product)
        data = {
            k: v for k, v in form.initial.items() if k in form.fields and v is not None
        }
        data.update(
            title="Changed Title",
            wizard_action="save_draft",
            variants_json=variants_json,
        )
        return self.client.post(
            reverse("wholesale:product_edit", args=[self.product.pk]), data
        )

    # INS7
    def test_bad_variant_payload_changes_nothing(self):
        resp = self._edit(json.dumps([{"title": "Red", "price": "abc"}]))
        self.assertEqual(resp.status_code, 200)  # form re-rendered with error
        self.product.refresh_from_db()
        self.assertEqual(self.product.title, "Sec Folder")
        self.assertEqual(self.product.approval_status, "PUBLISHED")
        self.assertTrue(ProductVariant.objects.filter(pk=self.variant.pk).exists())

    def test_valid_variant_payload_replaces_variants(self):
        resp = self._edit(json.dumps([{"title": "Red", "price": "5", "stock": 7}]))
        self.assertEqual(resp.status_code, 302)
        variants = list(self.product.variants.all())
        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0].name, "Red")
        self.assertEqual(variants[0].price_delta, Decimal("5"))
        self.assertEqual(variants[0].stock_quantity, 7)

    # INS10
    def test_toggle_requires_post(self):
        url = reverse("wholesale:product_toggle", args=[self.product.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.product.refresh_from_db()
        self.assertEqual(self.product.approval_status, "PUBLISHED")
        self.assertEqual(self.client.post(url).status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.approval_status, "PAUSED")

    def test_product_list_renders_toggle_form(self):
        resp = self.client.get(reverse("wholesale:wholesaler_products"))
        self.assertContains(resp, f'id="toggle-form-{self.product.pk}" method="post"')

    # INS12
    def _job(self, content, name="x.csv"):
        return BulkImportJob.objects.create(
            wholesaler=self.profile,
            file=SimpleUploadedFile(name, content.encode()),
            original_filename=name,
        )

    def test_unknown_category_is_row_error(self):
        job = BulkImportService.process_import_job(
            self._job(
                HEADER
                + "A,SKU-A,Sec Cat,10,1\nB,SKU-B,Nope,10,1\nC,SKU-C,,10,1\nD,WS-SEC-001,Sec Cat,10,1\n"
            )
        )
        self.assertEqual(job.status, "PARTIAL")
        # A ok, C (blank category) uses the default category as before; B unknown, D duplicate SKU.
        self.assertEqual((job.success_count, job.failed_count), (2, 2))
        self.assertTrue(WholesaleProduct.objects.filter(sku="SKU-C").exists())
        self.assertIn(
            "Unknown category",
            " ".join(job.errors.values_list("error_message", flat=True)),
        )
        self.assertTrue(
            WholesaleProduct.objects.filter(
                sku="SKU-A", category__name="Sec Cat"
            ).exists()
        )

    def test_duplicate_sku_within_file_rejected(self):
        job = BulkImportService.process_import_job(
            self._job(HEADER + "A,SKU-A,sec cat,10,1\nA2,SKU-A,Sec Cat,10,1\n")
        )
        self.assertEqual((job.success_count, job.failed_count), (1, 1))

    def test_row_cap_fails_job(self):
        rows = "".join(
            f"T{i},S{i},Sec Cat,10,1\n" for i in range(BulkImportService.MAX_ROWS + 1)
        )
        job = BulkImportService.process_import_job(self._job(HEADER + rows))
        self.assertEqual(job.status, "FAILED")
        self.assertIn("maximum is 2000", job.summary_message)
        self.assertFalse(WholesaleProduct.objects.filter(sku="S0").exists())

    def test_upload_view_size_cap_and_uppercase_extension(self):
        url = reverse("wholesale:bulk_upload")
        big = SimpleUploadedFile(
            "BIG.CSV", b"x" * (BulkImportService.MAX_FILE_BYTES + 1)
        )
        self.client.post(url, {"csv_file": big})
        self.assertFalse(BulkImportJob.objects.exists())
        ok = SimpleUploadedFile("UP.CSV", (HEADER + "A,SKU-UP,Sec Cat,10,1\n").encode())
        self.client.post(url, {"csv_file": ok})
        self.assertEqual(BulkImportJob.objects.get().status, "COMPLETED")
