# Hướng dẫn kết nối Cloudflare R2

## 1. Tạo tài khoản Cloudflare

Đăng ký tại [dash.cloudflare.com](https://dash.cloudflare.com) nếu chưa có tài khoản.

---

## 2. Tạo R2 Bucket

1. Vào **Cloudflare Dashboard** → chọn **R2 Object Storage** ở sidebar trái
2. Nhấn **Create bucket**
3. Đặt tên bucket (ví dụ: `my-image-service`) → **Create bucket**

---

## 3. Lấy Account ID

Account ID hiển thị ở góc phải sidebar khi bạn vào Dashboard, hoặc vào **R2 Object Storage** → URL sẽ có dạng:

```
https://dash.cloudflare.com/<ACCOUNT_ID>/r2
```

Đây chính là `R2_ACCOUNT_ID`.

---

## 4. Tạo API Token (Access Key)

1. Vào **R2 Object Storage** → tab **Manage R2 API Tokens**
2. Nhấn **Create API token**
3. Cấu hình:
   - **Token name**: đặt tên tuỳ ý (ví dụ: `image-service-token`)
   - **Permissions**: chọn **Object Read & Write**
   - **Specify bucket**: chọn bucket vừa tạo (hoặc All buckets)
4. Nhấn **Create API Token**
5. Trang kết quả sẽ hiển thị **một lần duy nhất**:
   - `Access Key ID` → đây là `R2_ACCESS_KEY_ID`
   - `Secret Access Key` → đây là `R2_SECRET_ACCESS_KEY`

> **Lưu ý:** Sao chép và lưu Secret Access Key ngay lập tức — Cloudflare sẽ không hiển thị lại sau khi bạn rời trang.

---

## 5. Lấy Public URL

Có hai cách để truy cập file công khai:

### Cách 1: Dùng domain mặc định của R2
Vào bucket → tab **Settings** → mục **Public access** → bật **Allow Access** → copy URL dạng:
```
https://pub-<hash>.r2.dev
```

### Cách 2: Dùng custom domain (khuyến nghị cho production)
Vào bucket → tab **Settings** → **Custom Domains** → thêm domain của bạn.

URL này chính là `R2_PUBLIC_URL`.

---

## 6. Cấu hình biến môi trường

Tạo file `.env` ở thư mục gốc dự án:

```env
DATABASE_URL=sqlite+aiosqlite:///./dev.db
JWT_SECRET=your-secret-key-here

R2_ACCOUNT_ID=abc123def456...
R2_ACCESS_KEY_ID=your-access-key-id
R2_SECRET_ACCESS_KEY=your-secret-access-key
R2_BUCKET_NAME=my-image-service
R2_PUBLIC_URL=https://pub-xxxx.r2.dev

REDIS_URL=redis://localhost:6379
```

---

## 7. Kiểm tra kết nối

Chạy đoạn script sau để xác nhận boto3 kết nối được với R2:

```python
import boto3
import os
from dotenv import load_dotenv

load_dotenv()

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
    aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
    region_name="auto",
)

# Liệt kê các bucket
response = s3.list_buckets()
print([b["Name"] for b in response["Buckets"]])
```

Nếu in ra tên bucket thì kết nối thành công.

---

## Tóm tắt các biến cần thiết

| Biến | Lấy ở đâu |
|---|---|
| `R2_ACCOUNT_ID` | Cloudflare Dashboard URL hoặc sidebar |
| `R2_ACCESS_KEY_ID` | R2 → Manage API Tokens → Create token |
| `R2_SECRET_ACCESS_KEY` | R2 → Manage API Tokens → Create token (chỉ hiện 1 lần) |
| `R2_BUCKET_NAME` | Tên bucket bạn đã tạo |
| `R2_PUBLIC_URL` | Bucket Settings → Public access hoặc Custom Domain |
