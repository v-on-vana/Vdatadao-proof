from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Global settings configuration using environment variables"""

    DLP_ID: int = Field(default=42, description="Data Liquidity Pool ID", ge=1)

    DLP_CONTRACT_ADDRESS: str = Field(
        default="0xdD29F495C058C7f13A7eb07428De3a46462E1909",
        description="Ethereum address of the DLP contract",
        pattern="^0x[a-fA-F0-9]{40}$",
    )

    FILE_ID: Optional[int] = Field(
        default=0, description="File ID in the Vana data registry"
    )

    OWNER_ADDRESS: Optional[str] = Field(
        default=None,
        description="Ethereum address of the data owner",
        pattern="^0x[a-fA-F0-9]{40}$",
    )

    RPC_URL: str = Field(
        default="https://rpc.vana.org",
        description="Vana RPC endpoint URL",
        pattern="^https?://.*$",
    )

    INPUT_DIR: str = Field(
        default="/input", description="Directory containing input files to process"
    )

    OUTPUT_DIR: str = Field(
        default="/output", description="Directory where output files will be written"
    )

    # PostgreSQL Configuration
    DATABASE_URL: Optional[str] = Field(
        default=None,
        description="PostgreSQL connection URL (postgresql://user:password@host:port/database)",
    )

    DB_HOST: str = Field(
        default="localhost",
        description="PostgreSQL host",
    )

    DB_PORT: int = Field(
        default=5432,
        description="PostgreSQL port",
    )

    DB_NAME: str = Field(
        default="vdatadao_proof",
        description="PostgreSQL database name",
    )

    DB_USER: str = Field(
        default="postgres",
        description="PostgreSQL username",
    )

    DB_PASSWORD: str = Field(
        default="",
        description="PostgreSQL password",
    )

    DOCKER_CONTAINER: bool = Field(
        default=False,
        description="Whether running inside Docker container",
    )

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
