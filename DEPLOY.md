# Deploy on Vercel (linked to GitHub)

Repo: https://github.com/shahzebtariq898-creator/website

## 1. Connect GitHub to Vercel

1. Open https://vercel.com and sign in with GitHub  
2. **Add New Project** → Import `shahzebtariq898-creator/website`  
3. Framework: **Flask** (auto-detected)  
4. Click **Deploy**

## 2. Environment variables (Vercel → Project → Settings → Environment Variables)

| Name | Value |
|------|--------|
| `SECRET_KEY` | any long random string |
| `MAIL_SERVER` | `smtp.gmail.com` |
| `MAIL_PORT` | `587` |
| `MAIL_USE_TLS` | `true` |
| `MAIL_USERNAME` | your Gmail |
| `MAIL_PASSWORD` | Gmail App Password |
| `MAIL_FROM` | same Gmail |

Redeploy after adding variables.

## 3. Live URL

After deploy: `https://website-xxx.vercel.app` (or your custom domain in Vercel).

Login: `shahzeb2003@gmail.com` / `12340000`

## CLI deploy (optional)

```bash
npm i -g vercel
cd website
vercel link
vercel --prod
```
