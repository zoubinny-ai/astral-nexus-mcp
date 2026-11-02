# Astral Nexus MCP

开源的星盘与八字确定性计算服务。独立运行，无需 Astral Nexus 主站、账号、数据库或付费报告接口。

## 安装

Python 3.11+，在本仓库根目录运行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python -m astral_nexus_mcp
```

Windows 使用 `.venv/Scripts/python.exe`。运行后等待 stdin 是正常行为。
暂未发布 npm 或 PyPI 安装包，不存在可用的 `npx` 安装命令。

## MCP 配置

将以下绝对路径替换为本机安装环境。安装后无需设置工作目录：

```json
{
  "mcpServers": {
    "astral-nexus": {
      "command": "/absolute/path/astral-nexus-mcp/.venv/bin/python",
      "args": ["-m", "astral_nexus_mcp"]
    }
  }
}
```

## 工具

- `calculate_astrology`：热带黄道本命星盘、星体位置、宫位、相位；宫制、交点及容许度复用计算设置。
- `calculate_bazi`：四柱、藏干、十神；默认真太阳时、23:00换日。可选大运／流年需传入排运性别与 `through_year`（1800–2399）。

调用参数示例（两种工具均可使用）：

```json
{
  "birth": {
    "birth_date": "2005-12-23",
    "local_time": "08:37",
    "timezone": "Asia/Shanghai",
    "location": {"latitude": 31.23, "longitude": 121.47},
    "sex": "M"
  }
}
```

返回 `service_id`、`engine_version`、`settings`、`result`、`limitations`。
只返回计算事实，不包含AI解读、格局取用判断、账户、支付或主站报告。
精确出生时间必填，夏令时重复／缺失时间拒绝猜测；星历缺失不自动降级或编造。
附带星历分片覆盖1800–2399；不保证每种宫制在极区均可计算。

规则辅助模块为现有计算链的依赖，不表示所有规则都作为MCP能力开放。
`SOURCE_MANIFEST.json`记录源文件与命名空间调整后的SHA256，可核对来源；仓库不含主站Git历史或配置。

## 测试

```sh
.venv/bin/python -m pip install '.[test]'
.venv/bin/python -m pytest -q
```

## 许可

本项目按 AGPL-3.0-only 发布，见 LICENSE。第三方依赖和星历的许可／来源见 THIRD_PARTY_NOTICES.md。
商业使用、修改与网络服务分发需遵守适用许可证，不能将本项目整体改称MIT。
