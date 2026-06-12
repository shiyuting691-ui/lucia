"""对象存储接口 · Cloudflare R2 预留 + 本地文件兜底

当前阶段所有上传文件都存在本地磁盘（uploads/ 目录）。
未来切换到 Cloudflare R2 时，只需在 .env 配置 R2_* 变量，
调用方代码不需要任何改动。

用法：
    from services.object_storage import get_storage
    storage = get_storage()
    key = storage.save("knowledge_base/产品手册.docx", file_bytes)
    data = storage.load(key)
"""

import os
from pathlib import Path


class LocalStorage:
    """本地磁盘存储（默认）。文件存放在项目 uploads/ 目录下。"""

    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir or Path(__file__).parent.parent / "uploads")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, data: bytes) -> str:
        path = self.base_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def load(self, key: str) -> bytes:
        return (self.base_dir / key).read_bytes()

    def exists(self, key: str) -> bool:
        return (self.base_dir / key).exists()

    def delete(self, key: str) -> None:
        path = self.base_dir / key
        if path.exists():
            path.unlink()

    def url(self, key: str) -> str:
        """本地存储没有公网 URL，返回文件路径。"""
        return str(self.base_dir / key)


class R2Storage:
    """Cloudflare R2 存储（S3 兼容接口）。

    需要 .env 配置：
        R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET_NAME
    依赖 boto3（requirements.txt 中按需添加）。
    """

    def __init__(self):
        import boto3  # 延迟导入，未启用 R2 时不要求安装

        account_id = os.environ["R2_ACCOUNT_ID"]
        self.bucket = os.environ["R2_BUCKET_NAME"]
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
        )

    def save(self, key: str, data: bytes) -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return key

    def load(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def url(self, key: str, expires: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires
        )


def get_storage():
    """根据环境变量自动选择存储后端：配齐 R2_* 用 R2，否则本地。"""
    required = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME")
    if all(os.environ.get(k) for k in required):
        return R2Storage()
    return LocalStorage()
