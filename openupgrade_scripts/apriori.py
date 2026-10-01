"""Encode any known changes to the database here
to help the matching process
"""

# Renamed modules is a mapping from old module name to new module name
renamed_modules = {
    # odoo
    "base_vat": "l10n_eu_account_vies",
    "purchase_requisition_sale": "purchase_alternative_sale",
    "website_sale_autocomplete": "website_address_autocomplete",
    # odoo/enterprise
    "ai_app": "ai_agentic",
    "esg_csrd_ai": "ai_esg",
    "l10n_din5008_industry_fsm": "l10n_din5008_planning_field_service",
    "mrp_workorder_iot": "mrp_iot",
    # OCA/...
}

# Merged modules contain a mapping from old module names to other,
# preexisting module names
merged_modules = {
    # odoo
    "account_add_gln": "account",
    "account_peppol_response": "account_peppol",
    "base_iban": "account",
    "delivery_stock_picking_batch": "stock_delivery",
    "hr_holidays_homeworking": "hr_holidays",
    "hr_homeworking": "hr",
    "hr_homeworking_calendar": "hr_calendar",
    "hr_hourly_cost": "hr",
    "hr_org_chart": "hr",
    "iot_base": "iot",
    "l10n_cn_city": "l10n_cn",
    "l10n_dk_nemhandel": "l10n_dk",
    "l10n_dk_nemhandel_response": "l10n_dk",
    "l10n_ro_cpv_code": "l10n_ro_edi",
    "l10n_ro_edi_stock_batch": "l10n_ro_edi_stock",
    "l10n_tr_nilvera_einvoice_extended": "l10n_tr_nilvera_einvoice",
    "pos_restaurant_adyen": "pos_adyen",
    "pos_restaurant_stripe": "pos_stripe",
    "stock_picking_batch": "stock",
    "theme_common": "website",
    "website_sale_collect_wishlist": "website_sale_collect",
    "website_sale_comparison": "website_sale",
    "website_sale_comparison_wishlist": "website_sale",
    "website_sale_stock_wishlist": "website_sale_stock",
    "website_sale_wishlist": "website_sale",
    # odoo/enterprise
    "account_accountant_batch_payment": "account_batch_payment",
    "esg_csrd": "esg",
    "esg_csrd_hr": "esg_hr",
    "esg_csrd_hr_fleet": "esg_hr_fleet",
    "hr_contract_salary_payroll": "hr_contract_salary",
    "hr_payroll_holidays": "hr_payroll",
    "hr_work_entry_enterprise": "hr_payroll",
    "l10n_ar_reports_simple": "l10n_ar",
    "l10n_be_hr_payroll_dimona": "l10n_be_hr_payroll",
    "l10n_be_hr_payroll_dimona_auto": "l10n_be_hr_payroll",
    "l10n_be_hr_payroll_fleet": "l10n_be_hr_payroll",
    "l10n_be_intervat": "l10n_be_reports",
    "l10n_br_edi_fiscal_reform": "l10n_br_edi",
    "l10n_br_edi_pos_fiscal_reform": "l10n_br_edi_pos",
    "l10n_br_edi_sale_fiscal_reform": "l10n_br_edi_sale",
    "l10n_br_website_sale_fiscal_reform": "l10n_br_edi_website_sale",
    "l10n_co_dian": "l10n_co_edi",
    "l10n_es_reports_2025": "l10n_es_reports",
    "l10n_hk_hr_payroll_empf": "l10n_hk_hr_payroll",
    "l10n_mx_hr_payroll_account_edi": "l10n_mx_hr_payroll_account",
    "l10n_mx_reports_closing": "l10n_mx_reports",
    "l10n_mx_xml_polizas": "l10n_mx_reports",
    "l10n_nl_returns": "l10n_nl_reports",
    "l10n_pl_reports_account_saft": "l10n_pl_reports",
    "l10n_pl_reports_jpk_fa": "l10n_pl_reports",
    "l10n_se_returns": "l10n_se_reports",
    "pos_urban_piper_ubereats": "pos_urban_piper",
    "quality_control_picking_batch": "quality_control",
    "quality_mrp_workorder_iot": "mrp_iot",
    "stock_barcode_picking_batch": "stock_barcode",
    "stock_barcode_quality_control_picking_batch": "stock_barcode_quality_control",
    # OCA/...
}

# only used here for upgrade_analysis
renamed_models = {
    # odoo
    "stock_account.stock.valuation.report": "account.stock.valuation.report",
    "website.base.unit": "product.base.unit",
    # OCA/...
}

# only used here for upgrade_analysis
merged_models = {
    # odoo
    "ir.model.access": "ir.access",
    "ir.rule": "ir.access",
    "product.template.attribute.exclusion": "product.template.attribute.value",
    "stock.scrap": "stock.move",
    # OCA/...
}

# Modules removed in 20.0 without a model/data successor (deliberately not mapped above,
# see migration20/docs/module_map_19_20.md):
# odoo
#   account_peppol_advanced_fields, delivery_mondialrelay, hr_work_entry_holidays, iot_box_image
#   l10n_dk_oioubl, l10n_ec_stock, l10n_fr_hr_work_entry_holidays, l10n_latam_base, l10n_sa_withholding_tax
#   l10n_tr_nilvera_base_vat, l10n_uy_pos, mrp_subcontracting_repair, pos_self_order_adyen
#   pos_self_order_stripe, transifex, website_sale_mondialrelay
# odoo/enterprise
#   account_winbooks_import, documents_fsm, esg_project, helpdesk_fsm, helpdesk_fsm_report
#   helpdesk_fsm_sale, hr_contract_salary_holidays, hr_payroll_planning, hr_payroll_sale_commission
#   hr_work_entry_attendance, hr_work_entry_holidays_enterprise, hr_work_entry_planning
#   hr_work_entry_planning_attendance, industry_fsm, industry_fsm_repair, industry_fsm_report
#   industry_fsm_sale, industry_fsm_sale_report, industry_fsm_sale_subscription, industry_fsm_sms
#   industry_fsm_stock, l10n_be_hr_payroll_acerta, l10n_be_hr_payroll_fix, l10n_be_hr_payroll_group_s
#   l10n_be_hr_payroll_partena, l10n_be_hr_payroll_prisma, l10n_be_hr_payroll_sd_worx
#   l10n_be_hr_payroll_ucm, l10n_be_reports_client_nihil, l10n_co_edi_mandate, l10n_es_reports_2024
#   l10n_fr_hr_payroll, l10n_fr_hr_payroll_account, l10n_it_hr_payroll_sd_worx, l10n_pk_reports
#   l10n_us_hr_payroll_adp, mrp_workorder_expiry, pos_blackbox_be, pos_iot_ingenico
#   pos_restaurant_urban_piper, pos_urban_piper_enhancements, voip_onsip
