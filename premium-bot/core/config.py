from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Premium Bot"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    domain: str = "localhost"
    cors_origins: str = "http://localhost:5173"
    api_prefix: str = "/api/v1"

    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_database: str = "premium_bot"
    mysql_user: str = "premium"
    mysql_password: str = "premium"
    database_url: str = ""

    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    jwt_secret: str = "dev-only-secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 30
    jwt_refresh_token_days: int = 7
    internal_api_token: str = "dev-internal-token"
    admin_username: str = "admin"
    admin_password: str = "ChangeMe_123!"

    telegram_bot_token: str = ""
    telegram_api_base_url: str = "http://api:8000/api/v1"

    order_expire_minutes: int = 30
    deposit_expire_minutes: int = 60
    wallet_min_deposit: str = "1"
    wallet_max_deposit: str = "10000"
    payment_unique_amount: bool = True
    payment_amount_scale: int = 4
    default_payment_network: str = "TRC20"
    enabled_payment_networks: str = "TRC20,BEP20"

    trc20_receive_address: str = ""
    bep20_receive_address: str = ""
    erc20_receive_address: str = ""

    trongrid_api_url: str = "https://api.trongrid.io"
    trongrid_api_key: str = ""
    bep20_rpc_url: str = ""
    erc20_rpc_url: str = ""
    bep20_usdt_contract: str = "0x55d398326f99059fF775485246999027B3197955"
    erc20_usdt_contract: str = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    trc20_usdt_contract: str = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    bep20_confirmations: int = 15
    erc20_confirmations: int = 20
    trc20_confirmations: int = 20
    payment_scan_block_chunk: int = 1500
    payment_webhook_secret: str = "dev-webhook-secret"

    premium_provider: str = "mock"
    allow_mock_premium_in_production: bool = False
    premium_provider_url: str = ""
    premium_provider_token: str = ""
    premium_provider_timeout_seconds: int = 20

    order_callback_secret: str = "dev-callback-secret"
    order_callback_timeout_seconds: int = 10
    refund_provider_url: str = ""
    refund_provider_token: str = ""

    # Fragment + TON hot-wallet risk policy. Private keys are intentionally not
    # configured here; signing must live in an isolated signer service.
    fragment_automation_enabled: bool = False
    ton_hot_wallet_count: int = 3
    ton_single_limit: str = "50"
    ton_global_daily_limit: str = "100"
    ton_wallet_daily_limit: str = "100"
    ton_manual_refill: bool = True
    ton_wallet_lock_seconds: int = 240
    ton_reservation_minutes: int = 10
    ton_circuit_failure_threshold: int = 3
    ton_circuit_cooldown_seconds: int = 900
    ton_known_destinations: str = ""
    ton_destination_policy: str = "dynamic"
    ton_require_exact_destination: bool = False
    ton_require_mainnet: bool = True
    ton_require_single_message: bool = True
    ton_require_payload: bool = True
    ton_allow_state_init: bool = False
    ton_allow_extra_currency: bool = False
    ton_amount_deviation_bps: int = 100
    ton_new_schema_action: str = "manual_review"
    ton_dynamic_real_signing_allowed: bool = False
    ton_signer_mode: str = "mock"
    ton_signer_url: str = "http://signer:9000"
    ton_signer_shared_secret: str = "dev-ton-signer-secret"
    ton_signer_timeout_seconds: int = 15
    ton_signer_max_clock_skew_seconds: int = 60
    ton_signer_wallet_codes: str = "ton-hot-1,ton-hot-2,ton-hot-3"
    ton_signer_wallet_addresses: str = ""
    ton_signer_backend: str = "mock"
    allow_mock_ton_signer_in_production: bool = False
    toncenter_v2_url: str = "https://toncenter.com/api/v2"
    toncenter_v3_url: str = "https://toncenter.com/api/v3"
    toncenter_api_key: str = ""
    ton_signer_key_dir: str = "/run/secrets/ton-wallets"
    ton_signer_send_mode: int = 3
    ton_require_source_match: bool = True
    fragment_capture_min_ttl_seconds: int = 10
    fragment_capture_max_ttl_seconds: int = 600

    # Stage 4.2 Fragment browser runner. The runner never receives TON private keys.
    fragment_runner_enabled: bool = False
    fragment_runner_url: str = "http://fragment-runner:9100"
    fragment_runner_token: str = "dev-fragment-runner-token"
    fragment_runner_mode: str = "observe"
    fragment_runner_headless: bool = True
    fragment_runner_poll_seconds: int = 5
    fragment_runner_lease_seconds: int = 180
    fragment_runner_profile_dir: str = "/data/profiles"
    fragment_runner_base_url: str = "https://fragment.com"
    fragment_runner_purchase_path: str = "/premium"
    fragment_runner_username_selector: str = ""
    fragment_runner_months_selector_template: str = ""
    fragment_runner_continue_selector: str = ""
    fragment_runner_timeout_seconds: int = 90
    fragment_runner_auto_click: bool = False

    # Stage 4.3 production runner observability and recovery.
    fragment_runner_version: str = "4.3.0"
    fragment_runner_artifact_dir: str = "/data/fragment-artifacts"
    fragment_runner_runtime_dir: str = "/data/fragment-runtime"
    fragment_runner_selector_file: str = "/app/fragment_runner/selectors.json"
    fragment_runner_self_check: bool = True
    fragment_runner_screenshot_enabled: bool = True
    fragment_runner_trace_enabled: bool = True
    fragment_runner_html_snapshot_enabled: bool = True
    fragment_runner_heartbeat_seconds: int = 15
    fragment_runner_stale_seconds: int = 60
    fragment_runner_max_attempts: int = 6
    fragment_runner_retry_base_seconds: int = 10
    fragment_runner_retry_max_seconds: int = 600
    fragment_runner_account_lease_seconds: int = 300
    fragment_runner_accounts: str = "fragment-01=fragment-01"
    fragment_runner_alert_chat_ids: str = ""
    fragment_runner_alert_cooldown_seconds: int = 900
    fragment_runner_login_required_selector: str = ""
    fragment_runner_logged_in_selector: str = ""

    @field_validator("default_payment_network")
    @classmethod
    def uppercase_network(cls, value: str) -> str:
        return value.upper()

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url:
            return self.database_url
        return URL.create(
            "mysql+asyncmy",
            username=self.mysql_user,
            password=self.mysql_password,
            host=self.mysql_host,
            port=self.mysql_port,
            database=self.mysql_database,
            query={"charset": "utf8mb4"},
        ).render_as_string(hide_password=False)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def enabled_network_list(self) -> list[str]:
        return [network.strip().upper() for network in self.enabled_payment_networks.split(",")]

    @property
    def ton_known_destination_list(self) -> list[str]:
        return [address.strip() for address in self.ton_known_destinations.split(",") if address.strip()]

    @property
    def ton_signer_wallet_code_list(self) -> list[str]:
        return [code.strip() for code in self.ton_signer_wallet_codes.split(",") if code.strip()]

    @property
    def ton_signer_wallet_address_map(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in self.ton_signer_wallet_addresses.split(","):
            if "=" not in item:
                continue
            code, address = item.split("=", 1)
            code = code.strip()
            address = address.strip()
            if code and address:
                result[code] = address
        return result

    @property
    def fragment_runner_account_list(self) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        for item in self.fragment_runner_accounts.split(","):
            item = item.strip()
            if not item:
                continue
            if "=" in item:
                code, profile = item.split("=", 1)
            else:
                code = profile = item
            code, profile = code.strip(), profile.strip()
            if code and profile:
                result.append((code, profile))
        return result

    @property
    def fragment_runner_alert_chat_id_list(self) -> list[str]:
        return [item.strip() for item in self.fragment_runner_alert_chat_ids.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def validate_production_secrets(self) -> None:
        if not self.is_production:
            return
        values = {
            "JWT_SECRET": self.jwt_secret,
            "INTERNAL_API_TOKEN": self.internal_api_token,
            "PAYMENT_WEBHOOK_SECRET": self.payment_webhook_secret,
            "ADMIN_PASSWORD": self.admin_password,
            "TON_SIGNER_SHARED_SECRET": self.ton_signer_shared_secret,
            "FRAGMENT_RUNNER_TOKEN": self.fragment_runner_token,
        }
        invalid = [
            name for name, value in values.items() if "CHANGE_ME" in value or len(value) < 16
        ]
        if invalid:
            raise RuntimeError(f"Unsafe production secrets: {', '.join(invalid)}")
        provider = self.premium_provider.lower()
        if provider == "mock" and not self.allow_mock_premium_in_production:
            raise RuntimeError(
                "Mock Premium provider is disabled in production. "
                "Configure the webhook provider or explicitly allow mock mode."
            )
        if provider == "webhook" and (
            not self.premium_provider_url or len(self.premium_provider_token) < 16
        ):
            raise RuntimeError(
                "PREMIUM_PROVIDER_URL and a strong PREMIUM_PROVIDER_TOKEN are required"
            )
        signer_mode = self.ton_signer_mode.lower()
        if self.fragment_automation_enabled and signer_mode in {"remote", "remote_mock"}:
            if self.ton_signer_shared_secret.startswith("dev-") or len(
                self.ton_signer_shared_secret
            ) < 32:
                raise RuntimeError("A strong TON_SIGNER_SHARED_SECRET is required")
        if (
            self.fragment_automation_enabled
            and self.ton_signer_backend.lower() == "real"
            and self.ton_destination_policy.lower() == "dynamic"
            and not self.ton_dynamic_real_signing_allowed
        ):
            raise RuntimeError(
                "Dynamic-destination real signing is disabled. "
                "Set TON_DYNAMIC_REAL_SIGNING_ALLOWED=true only after controlled validation."
            )
        if self.fragment_runner_enabled and (
            self.fragment_runner_token.startswith("dev-")
            or len(self.fragment_runner_token) < 32
        ):
            raise RuntimeError("A strong FRAGMENT_RUNNER_TOKEN is required")
        if self.fragment_runner_enabled and not self.fragment_runner_account_list:
            raise RuntimeError("At least one FRAGMENT_RUNNER_ACCOUNTS entry is required")
        if (
            self.fragment_automation_enabled
            and signer_mode in {"mock", "local_mock", "remote_mock"}
            and not self.allow_mock_ton_signer_in_production
        ):
            raise RuntimeError(
                "Mock TON signer is disabled in production; explicitly allow it for testing"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
