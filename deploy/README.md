# 部署说明

1. 后端：`docker compose -f docker/docker-compose.yml up -d`，或 `uvicorn app.factory:app --host 0.0.0.0 --port 8000`
2. Nginx：把 `nginx.conf` 拷到 `/etc/nginx/conf.d/`，前端静态文件放 `/var/www/bilingual-ebook-web`
3. 生产环境务必修改 `.env` 中的 `SECRET_KEY`
