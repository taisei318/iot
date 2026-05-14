"""
ftp.py
FTP アップロード用ユーティリティ。receiver.py から関数として呼ばれる。
このファイル単体で実行すると ex.csv をテスト送信する。
"""
from ftplib import FTP

FTP_HOST = "172.31.202.182"
FTP_USER = "user"
FTP_PASS = "password"
FTP_REMOTE_DIR = "/"  # ftp_server.py 側で指定した RECV_DIR がサーバのルートになる


def upload(local_path: str, remote_name: str) -> None:
    ftp = FTP(FTP_HOST)
    ftp.login(FTP_USER, FTP_PASS)
    ftp.cwd(FTP_REMOTE_DIR)
    with open(local_path, "rb") as f:
        ftp.storbinary(f"STOR {remote_name}", f)
    ftp.quit()


if __name__ == "__main__":
    upload("ex.csv", "ex_rcv.csv")
    print("uploaded")
