import os
import pyzipper


def encrypt_file_to_zip(input_path: str, zip_path: str, password: str) -> None:
    """Encrypt one file into an AES ZIP archive."""
    if not os.path.exists(input_path):
        return

    parent = os.path.dirname(zip_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with pyzipper.AESZipFile(
        zip_path,
        "w",
        compression=pyzipper.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
    ) as zf:
        zf.setpassword(password.encode("utf-8"))
        zf.write(input_path, arcname=os.path.basename(input_path))


def decrypt_zip_to_file(zip_path: str, output_dir: str, password: str) -> str | None:
    """Decrypt an AES ZIP archive and return the extracted file path."""
    if not os.path.exists(zip_path):
        return None

    os.makedirs(output_dir, exist_ok=True)

    with pyzipper.AESZipFile(zip_path, "r") as zf:
        zf.setpassword(password.encode("utf-8"))
        names = zf.namelist()
        if not names:
            return None
        zf.extractall(output_dir)
        return os.path.join(output_dir, names[0])
