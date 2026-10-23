# 门面站部署

这是 `cyberdyne-bridge.com` 的静态门面：只放项目摘要和仓库链接，不镜像文档、不接本地服务、不放运行数据。

## 本地预览

```bash
python3 -m http.server 8000 --directory site
# http://127.0.0.1:8000
```

## GitHub Pages（推荐）

仓库已带 `.github/workflows/pages.yml`：

1. GitHub 仓库 → Settings → Pages
2. Build and deployment → Source 选 **GitHub Actions**
3. 先启用 Pages；否则 `deploy-pages` 会报 “Pages site not found”
4. push 到 `main`，或在 Actions 里手动跑 `Deploy site`
4. Custom domain 填 `www.cyberdyne-bridge.com`
5. 勾选 **Enforce HTTPS**

`site/CNAME` 已写好：

```text
www.cyberdyne-bridge.com
```

## 阿里云 DNS（当前注册商）

在阿里云 → 云解析 DNS → `cyberdyne-bridge.com` 添加：

```text
记录类型    主机记录    记录值
CNAME       www         6750432.github.io
A           @           185.199.108.153
A           @           185.199.109.153
A           @           185.199.110.153
A           @           185.199.111.153
```

如果阿里云云解析支持 URL 转发，也可以让 `@` 301 到：

```text
https://www.cyberdyne-bridge.com
```

DNS 生效后再回 GitHub Pages 点一次 Custom domain 的保存/验证。HTTPS 证书由 GitHub Pages 自动签发，不用在阿里云开 SSL。

## 换 Cloudflare Pages（可选）

如果以后想 apex + www 更省心，可以把域名的 NS 从 `dns31.hichina.com` / `dns32.hichina.com` 改到 Cloudflare，再用 Cloudflare Pages 连这个仓库，输出目录填 `site`。

## 边界

```text
不接 25565 / 8765 / RCON / 车钩 socket
不放日志、记忆、任务栈、key
站点内容只来自公开仓库
```
