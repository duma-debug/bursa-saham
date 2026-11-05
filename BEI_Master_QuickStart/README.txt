BEI FINANCIAL MASTER QUICKSTART
==============================
1. Extract folder BEI_Master_QuickStart into C:\Analisis_Saham_BEI.
2. Confirm three inputs exist in C:\Analisis_Saham_BEI:
   financial_production.db
   financial_modeling_v4_1.db
   financial_legacy_v4_6.db
3. CMD:
   cd /d C:\Analisis_Saham_BEI\BEI_Master_QuickStart
   py bei_master_quickstart.py --base "C:\Analisis_Saham_BEI" --ticker AALI
4. Open C:\Analisis_Saham_BEI\BEI_Master_Output:
   BEI_Financial_Master.db
   master_report.json
   AALI_content_snapshot_REVIEW.csv
   AALI_legacy_2022_REVIEW.csv
   AALI_article_brief.md
5. Output is REVIEW-ONLY. Source databases, PDFs and Excel are not deleted or modified. Do not publish raw numeric values before reconciling scale, period, and account semantics. If rerunning, archive or rename BEI_Financial_Master.db first; tool never overwrites.
6. For another ticker use --ticker BBCA (subject to current mapping limitations).
