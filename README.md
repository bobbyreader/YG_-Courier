# 内网 IT 运维系统 RPA 机器人

## 环境准备

```powershell
# 1. 安装依赖
pip install -r requirements.txt

# 2. 安装 Playwright 浏览器
playwright install chromium

# 3. 配置账号
 copy .env.example .env
# 编辑 .env 填入用户名密码
```

## 运行

```powershell
python rpa_bot.py
```

## 关键配置：自签名证书

已在 `config.py` 和 `rpa_bot.py` 中设置：
- `ignore_https_errors=True`
- `--ignore-certificate-errors` 启动参数

## 下一步

1. 先运行一次，看能否打开登录页
2. 用 Playwright 的 `codegen` 录制选择器：
   ```powershell
   playwright codegen https://www.zhyw.spic/login/?c_url=/ --ignore-https-errors
   ```
3. 把录制的选择器更新到 `config.py`
4. 实现 `submit_ticket` 方法
