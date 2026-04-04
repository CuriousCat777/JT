"""Tests for Teller, bank CSV, and OFX providers + CFO integration."""

from pathlib import Path

import pytest

from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig
from guardian_one.agents.cfo import (
    CFO,
    AccountType,
)
from guardian_one.integrations.financial_sync import (
    TellerProvider,
    SyncedAccount,
    SyncedTransaction,
    parse_bank_csv,
    parse_ofx,
    _map_teller_account_type,
    _map_teller_category,
    _normalize_date,
    _parse_amount,
    _map_ofx_account_type,
    _map_ofx_tx_type,
    _sgml_ofx_to_xml,
    _parse_ofx_date,
)


# Env vars that could cause real network calls if set in CI/dev
_FINANCIAL_ENV_VARS = (
    "TELLER_ACCESS_TOKEN", "TELLER_ENVIRONMENT",
    "PLAID_CLIENT_ID", "PLAID_SECRET", "PLAID_ENV",
    "ROCKET_MONEY_API_KEY", "EMPOWER_API_KEY",
    "EMPOWER_USERNAME", "EMPOWER_PASSWORD",
)


@pytest.fixture(autouse=True)
def _clean_financial_env(monkeypatch):
    """Strip financial provider env vars so tests never make real API calls."""
    for var in _FINANCIAL_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def audit(tmp_path):
    return AuditLog(log_dir=tmp_path / "audit")


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir(exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Teller provider
# ---------------------------------------------------------------------------

class TestTellerProvider:
    def test_no_credentials(self):
        provider = TellerProvider(access_token="")
        assert not provider.has_credentials
        assert provider.provider_name == "teller"
        assert not provider.authenticate()
        assert "TELLER_ACCESS_TOKEN" in provider.last_error

    def test_has_credentials(self):
        provider = TellerProvider(access_token="test_token_123")
        assert provider.has_credentials

    def test_status_offline(self):
        provider = TellerProvider(access_token="")
        status = provider.status()
        assert status["provider"] == "teller"
        assert not status["has_credentials"]
        assert not status["authenticated"]

    def test_status_with_token(self):
        provider = TellerProvider(access_token="tok_123", env="sandbox")
        status = provider.status()
        assert status["has_credentials"]
        assert status["environment"] == "sandbox"
        assert status["enrollments"] == 0

    def test_fetch_accounts_not_authenticated(self):
        provider = TellerProvider(access_token="tok_123")
        assert provider.fetch_accounts() == []

    def test_fetch_transactions_not_authenticated(self):
        provider = TellerProvider(access_token="tok_123")
        assert provider.fetch_transactions("2026-01-01", "2026-03-31") == []

    def test_connected_institutions_empty(self):
        provider = TellerProvider(access_token="tok_123")
        assert provider.connected_institutions == []


class TestTellerMappings:
    def test_account_type_depository(self):
        assert _map_teller_account_type("depository", "") == "checking"
        assert _map_teller_account_type("depository", "checking") == "checking"
        assert _map_teller_account_type("depository", "savings") == "savings"
        assert _map_teller_account_type("depository", "money_market") == "savings"

    def test_account_type_credit(self):
        assert _map_teller_account_type("credit", "") == "credit_card"
        assert _map_teller_account_type("credit", "credit_card") == "credit_card"

    def test_account_type_retirement(self):
        assert _map_teller_account_type("investment", "401k") == "retirement"
        assert _map_teller_account_type("investment", "ira") == "retirement"
        assert _map_teller_account_type("investment", "roth") == "retirement"
        assert _map_teller_account_type("investment", "roth_401k") == "retirement"

    def test_account_type_investment(self):
        assert _map_teller_account_type("investment", "brokerage") == "investment"
        assert _map_teller_account_type("investment", "") == "investment"

    def test_account_type_loan(self):
        assert _map_teller_account_type("loan", "") == "loan"
        assert _map_teller_account_type("loan", "mortgage") == "loan"
        assert _map_teller_account_type("loan", "student") == "loan"

    def test_account_type_unknown(self):
        assert _map_teller_account_type("unknown", "") == "checking"

    def test_category_deposit(self):
        assert _map_teller_category("deposit") == "income"

    def test_category_interest(self):
        assert _map_teller_category("interest") == "income"

    def test_category_transfer(self):
        assert _map_teller_category("transfer") == "savings"

    def test_category_unknown(self):
        assert _map_teller_category("something_else") == "other"
        assert _map_teller_category("") == "other"


# ---------------------------------------------------------------------------
# Generic bank CSV importer
# ---------------------------------------------------------------------------

class TestBankCSV:
    def test_parse_basic_csv(self, tmp_path):
        csv_file = tmp_path / "chase_checking.csv"
        csv_file.write_text(
            "Date,Description,Amount\n"
            "01/15/2026,PAYCHECK DEPOSIT,2500.00\n"
            "01/16/2026,GROCERY STORE,-85.50\n"
            "01/17/2026,GAS STATION,-42.00\n"
        )
        accounts, transactions = parse_bank_csv(csv_file, institution="Chase")
        assert len(accounts) == 1
        assert accounts[0].institution == "Chase"
        assert accounts[0].balance == 0.0  # no balance column → 0 (don't corrupt net worth)
        assert len(transactions) == 3
        assert transactions[0].amount == 2500.00
        assert transactions[1].amount == -85.50

    def test_parse_csv_with_balance_column(self, tmp_path):
        csv_file = tmp_path / "bank.csv"
        csv_file.write_text(
            "Date,Description,Amount,Balance\n"
            "2026-01-15,PAYCHECK,2500,5000.00\n"
            "2026-01-16,RENT,-1200,3800.00\n"
        )
        accounts, _ = parse_bank_csv(csv_file)
        assert accounts[0].balance == 3800.00  # last row's balance column

    def test_parse_debit_credit_columns(self, tmp_path):
        csv_file = tmp_path / "bofa_statement.csv"
        csv_file.write_text(
            "Date,Description,Debit,Credit\n"
            "2026-01-15,Direct Deposit,,3000.00\n"
            "2026-01-16,Electric Bill,150.00,\n"
        )
        accounts, txns = parse_bank_csv(csv_file, institution="Bank of America")
        assert len(txns) == 2
        assert txns[0].amount == 3000.00  # credit
        assert txns[1].amount == -150.00  # debit

    def test_auto_detect_institution_from_filename(self, tmp_path):
        csv_file = tmp_path / "wells_fargo_checking_2026.csv"
        csv_file.write_text("Date,Description,Amount\n2026-01-01,Test,100\n")
        accounts, _ = parse_bank_csv(csv_file)
        assert accounts[0].institution == "Wells Fargo"

    def test_auto_detect_chase(self, tmp_path):
        csv_file = tmp_path / "chase_transactions.csv"
        csv_file.write_text("Date,Description,Amount\n2026-01-01,Test,50\n")
        accounts, _ = parse_bank_csv(csv_file)
        assert accounts[0].institution == "Chase"

    def test_auto_detect_bofa(self, tmp_path):
        csv_file = tmp_path / "bofa_checking.csv"
        csv_file.write_text("Date,Description,Amount\n2026-01-01,Test,50\n")
        accounts, _ = parse_bank_csv(csv_file)
        assert accounts[0].institution == "Bank of America"

    def test_auto_detect_us_bank(self, tmp_path):
        csv_file = tmp_path / "us_bank_statement.csv"
        csv_file.write_text("Date,Description,Amount\n2026-01-01,Test,50\n")
        accounts, _ = parse_bank_csv(csv_file)
        assert accounts[0].institution == "US Bank"

    def test_empty_csv(self, tmp_path):
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("Date,Description,Amount\n")
        accounts, txns = parse_bank_csv(csv_file)
        assert accounts == []
        assert txns == []

    def test_nonexistent_file(self):
        accounts, txns = parse_bank_csv("/nonexistent/path.csv")
        assert accounts == []
        assert txns == []

    def test_posting_date_column(self, tmp_path):
        csv_file = tmp_path / "bank.csv"
        csv_file.write_text("Posting Date,Memo,Amount\n01/20/2026,RENT,-1200\n")
        accounts, txns = parse_bank_csv(csv_file)
        assert len(txns) == 1
        assert txns[0].date == "2026-01-20"

    def test_parentheses_negative(self, tmp_path):
        csv_file = tmp_path / "bank.csv"
        csv_file.write_text("Date,Description,Amount\n2026-01-01,Refund,($50.00)\n")
        accounts, txns = parse_bank_csv(csv_file)
        assert txns[0].amount == -50.00

    def test_custom_account_info(self, tmp_path):
        csv_file = tmp_path / "export.csv"
        csv_file.write_text("Date,Description,Amount\n2026-01-01,Test,100\n")
        accounts, _ = parse_bank_csv(
            csv_file,
            institution="Ally Bank",
            account_name="Ally Savings",
            account_type="savings",
        )
        assert accounts[0].name == "Ally Savings"
        assert accounts[0].institution == "Ally Bank"
        assert accounts[0].account_type == "savings"


class TestDateNormalization:
    def test_iso_format(self):
        assert _normalize_date("2026-01-15") == "2026-01-15"

    def test_us_format(self):
        assert _normalize_date("01/15/2026") == "2026-01-15"
        assert _normalize_date("1/5/2026") == "2026-01-05"

    def test_short_year(self):
        assert _normalize_date("01/15/26") == "2026-01-15"
        assert _normalize_date("12/31/99") == "1999-12-31"

    def test_day_mon_year(self):
        assert _normalize_date("15-Jan-2026") == "2026-01-15"

    def test_passthrough(self):
        assert _normalize_date("not a date") == "not a date"


class TestParseAmount:
    def test_basic(self):
        assert _parse_amount("100.50") == 100.50
        assert _parse_amount("-50") == -50.0

    def test_currency_symbol(self):
        assert _parse_amount("$1,234.56") == 1234.56

    def test_parentheses_negative(self):
        assert _parse_amount("(500.00)") == -500.00

    def test_empty(self):
        assert _parse_amount("") == 0.0
        assert _parse_amount("   ") == 0.0

    def test_invalid(self):
        assert _parse_amount("abc") == 0.0


# ---------------------------------------------------------------------------
# OFX / QFX importer
# ---------------------------------------------------------------------------

class TestOFX:
    def _make_ofx_xml(self) -> str:
        return """<?xml version="1.0" encoding="UTF-8"?>
<OFX>
  <BANKMSGSRSV1>
    <STMTTRNRS>
      <STMTRS>
        <CURDEF>USD</CURDEF>
        <BANKACCTFROM>
          <BANKID>021000021</BANKID>
          <ACCTID>1234567890</ACCTID>
          <ACCTTYPE>CHECKING</ACCTTYPE>
        </BANKACCTFROM>
        <BANKTRANLIST>
          <DTSTART>20260101</DTSTART>
          <DTEND>20260131</DTEND>
          <STMTTRN>
            <TRNTYPE>CREDIT</TRNTYPE>
            <DTPOSTED>20260115</DTPOSTED>
            <TRNAMT>2500.00</TRNAMT>
            <NAME>PAYCHECK</NAME>
          </STMTTRN>
          <STMTTRN>
            <TRNTYPE>DEBIT</TRNTYPE>
            <DTPOSTED>20260116</DTPOSTED>
            <TRNAMT>-85.50</TRNAMT>
            <MEMO>GROCERY STORE</MEMO>
          </STMTTRN>
        </BANKTRANLIST>
        <LEDGERBAL>
          <BALAMT>5432.10</BALAMT>
          <DTASOF>20260131</DTASOF>
        </LEDGERBAL>
      </STMTRS>
    </STMTTRNRS>
  </BANKMSGSRSV1>
</OFX>"""

    def test_parse_xml_ofx(self, tmp_path):
        ofx_file = tmp_path / "statement.ofx"
        ofx_file.write_text(self._make_ofx_xml())
        accounts, txns = parse_ofx(ofx_file)
        assert len(accounts) == 1
        assert accounts[0].account_type == "checking"
        assert accounts[0].balance == 5432.10
        assert "***7890" in accounts[0].name
        assert len(txns) == 2
        assert txns[0].amount == 2500.00
        assert txns[0].description == "PAYCHECK"
        assert txns[0].date == "2026-01-15"
        assert txns[1].amount == -85.50
        assert txns[1].description == "GROCERY STORE"

    def test_parse_credit_card_ofx(self, tmp_path):
        ofx_content = """<?xml version="1.0" encoding="UTF-8"?>
<OFX>
  <CREDITCARDMSGSRSV1>
    <CCSTMTTRNRS>
      <CCSTMTRS>
        <CURDEF>USD</CURDEF>
        <CCACCTFROM>
          <ACCTID>4111111111111111</ACCTID>
        </CCACCTFROM>
        <BANKTRANLIST>
          <STMTTRN>
            <TRNTYPE>DEBIT</TRNTYPE>
            <DTPOSTED>20260120</DTPOSTED>
            <TRNAMT>-45.99</TRNAMT>
            <NAME>RESTAURANT</NAME>
          </STMTTRN>
        </BANKTRANLIST>
        <LEDGERBAL>
          <BALAMT>-1250.00</BALAMT>
        </LEDGERBAL>
      </CCSTMTRS>
    </CCSTMTTRNRS>
  </CREDITCARDMSGSRSV1>
</OFX>"""
        ofx_file = tmp_path / "cc.ofx"
        ofx_file.write_text(ofx_content)
        accounts, txns = parse_ofx(ofx_file)
        assert len(accounts) == 1
        assert accounts[0].account_type == "credit_card"
        assert accounts[0].balance == -1250.00
        assert len(txns) == 1
        assert txns[0].amount == -45.99

    def test_nonexistent_file(self):
        accounts, txns = parse_ofx("/nonexistent/path.ofx")
        assert accounts == []
        assert txns == []

    def test_empty_file(self, tmp_path):
        ofx_file = tmp_path / "empty.ofx"
        ofx_file.write_text("")
        accounts, txns = parse_ofx(ofx_file)
        assert accounts == []
        assert txns == []

    def test_invalid_xml(self, tmp_path):
        ofx_file = tmp_path / "bad.ofx"
        ofx_file.write_text("this is not xml or ofx")
        accounts, txns = parse_ofx(ofx_file)
        assert accounts == []
        assert txns == []


class TestOFXMappings:
    def test_account_types(self):
        assert _map_ofx_account_type("CHECKING") == "checking"
        assert _map_ofx_account_type("SAVINGS") == "savings"
        assert _map_ofx_account_type("CREDITCARD") == "credit_card"
        assert _map_ofx_account_type("CREDITLINE") == "credit_card"
        assert _map_ofx_account_type("MONEYMRKT") == "savings"
        assert _map_ofx_account_type("UNKNOWN") == "checking"

    def test_tx_types(self):
        assert _map_ofx_tx_type("credit") == "income"
        assert _map_ofx_tx_type("dep") == "income"
        assert _map_ofx_tx_type("directdep") == "income"
        assert _map_ofx_tx_type("xfer") == "savings"
        assert _map_ofx_tx_type("debit") == "other"
        assert _map_ofx_tx_type("unknown") == "other"

    def test_ofx_date_parsing(self):
        assert _parse_ofx_date("20260115") == "2026-01-15"
        assert _parse_ofx_date("20260115120000") == "2026-01-15"
        assert _parse_ofx_date("20260115120000[0:GMT]") == "2026-01-15"
        assert _parse_ofx_date("20260115[-5:EST]") == "2026-01-15"


class TestSGMLConversion:
    def test_basic_conversion(self):
        sgml = """OFXHEADER:100
<OFX>
<BANKMSGSRSV1>
<STMTTRNRS>
<TRNUID>12345
<STMTRS>
<BANKACCTFROM>
<BANKID>021000021
<ACCTID>999888777
<ACCTTYPE>CHECKING
</BANKACCTFROM>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>"""
        xml = _sgml_ofx_to_xml(sgml)
        assert "<BANKID>021000021</BANKID>" in xml
        assert "<ACCTID>999888777</ACCTID>" in xml
        assert "<ACCTTYPE>CHECKING</ACCTTYPE>" in xml


# ---------------------------------------------------------------------------
# CFO integration
# ---------------------------------------------------------------------------

class TestCFOTellerIntegration:
    def test_cfo_has_teller(self, audit, data_dir):
        cfo = CFO(config=AgentConfig(name="cfo"), audit=audit, data_dir=data_dir)
        assert hasattr(cfo, '_teller')
        assert hasattr(cfo, '_teller_connected')
        assert isinstance(cfo.teller, TellerProvider)

    def test_teller_status(self, audit, data_dir):
        cfo = CFO(config=AgentConfig(name="cfo"), audit=audit, data_dir=data_dir)
        status = cfo.teller_status()
        assert status["provider"] == "teller"
        assert "connected" in status

    def test_sync_teller_not_connected(self, audit, data_dir):
        cfo = CFO(config=AgentConfig(name="cfo"), audit=audit, data_dir=data_dir)
        result = cfo.sync_teller()
        assert result["source"] == "teller"
        assert not result["connected"]

    def test_sync_all_includes_teller(self, audit, data_dir):
        cfo = CFO(config=AgentConfig(name="cfo"), audit=audit, data_dir=data_dir)
        cfo.initialize()
        results = cfo.sync_all()
        assert "teller" in results
        assert results["teller"]["source"] == "teller"
        # sync_all returns a dict with net_worth key as well
        assert "net_worth" in results


class TestCFOCSVImport:
    def test_import_bank_csv(self, tmp_path, audit, data_dir):
        csv_file = tmp_path / "chase.csv"
        csv_file.write_text(
            "Date,Description,Amount\n"
            "2026-01-15,PAYCHECK,2500\n"
            "2026-01-16,RENT,-1200\n"
        )
        cfo = CFO(config=AgentConfig(name="cfo"), audit=audit, data_dir=data_dir)
        cfo.initialize()

        result = cfo.import_bank_csv(csv_file, institution="Chase")
        assert result["source"] == "bank_csv"
        assert result["accounts_added"] == 1
        assert result["transactions_added"] == 2


class TestCFOOFXImport:
    def test_import_ofx(self, tmp_path, audit, data_dir):
        ofx_file = tmp_path / "statement.ofx"
        ofx_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<OFX>
  <BANKMSGSRSV1>
    <STMTTRNRS>
      <STMTRS>
        <BANKACCTFROM>
          <BANKID>021000021</BANKID>
          <ACCTID>1234567890</ACCTID>
          <ACCTTYPE>CHECKING</ACCTTYPE>
        </BANKACCTFROM>
        <BANKTRANLIST>
          <STMTTRN>
            <TRNTYPE>CREDIT</TRNTYPE>
            <DTPOSTED>20260115</DTPOSTED>
            <TRNAMT>3000.00</TRNAMT>
            <NAME>DIRECT DEPOSIT</NAME>
          </STMTTRN>
        </BANKTRANLIST>
        <LEDGERBAL>
          <BALAMT>5000.00</BALAMT>
        </LEDGERBAL>
      </STMTRS>
    </STMTTRNRS>
  </BANKMSGSRSV1>
</OFX>""")
        cfo = CFO(config=AgentConfig(name="cfo"), audit=audit, data_dir=data_dir)
        cfo.initialize()

        result = cfo.import_ofx(ofx_file)
        assert result["source"] == "ofx"
        assert result["accounts_added"] == 1
        assert result["transactions_added"] == 1

    def test_import_deduplicates(self, tmp_path, audit, data_dir):
        ofx_file = tmp_path / "statement.ofx"
        ofx_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<OFX>
  <BANKMSGSRSV1>
    <STMTTRNRS>
      <STMTRS>
        <BANKACCTFROM>
          <BANKID>021000021</BANKID>
          <ACCTID>9999</ACCTID>
          <ACCTTYPE>CHECKING</ACCTTYPE>
        </BANKACCTFROM>
        <BANKTRANLIST>
          <STMTTRN>
            <TRNTYPE>CREDIT</TRNTYPE>
            <DTPOSTED>20260115</DTPOSTED>
            <TRNAMT>1000.00</TRNAMT>
            <NAME>DEPOSIT</NAME>
          </STMTTRN>
        </BANKTRANLIST>
        <LEDGERBAL><BALAMT>1000.00</BALAMT></LEDGERBAL>
      </STMTRS>
    </STMTTRNRS>
  </BANKMSGSRSV1>
</OFX>""")
        cfo = CFO(config=AgentConfig(name="cfo"), audit=audit, data_dir=data_dir)
        cfo.initialize()

        result1 = cfo.import_ofx(ofx_file)
        assert result1["transactions_added"] == 1

        result2 = cfo.import_ofx(ofx_file)
        assert result2["transactions_added"] == 0  # no duplicates
        assert result2["accounts_updated"] == 1


class TestCFODashboardIncludesTeller:
    def test_dashboard_has_teller(self, audit, data_dir):
        cfo = CFO(config=AgentConfig(name="cfo"), audit=audit, data_dir=data_dir)
        cfo.initialize()
        dashboard = cfo.dashboard()
        assert "teller" in dashboard

    def test_validation_report_has_teller(self, audit, data_dir):
        cfo = CFO(config=AgentConfig(name="cfo"), audit=audit, data_dir=data_dir)
        cfo.initialize()
        report = cfo.validation_report()
        assert "teller" in report
