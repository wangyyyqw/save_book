# qidian_save

起点中文网书籍本地保存工具。

## 免责声明

本工具用于备份用户在起点中文网已购买的章节内容，仅限个人合法使用。
用户应自行遵守起点中文网服务条款。
开发者不对用户的使用行为承担任何责任。

## 快速开始

```bash
pip install qidian-save

# 设置服务端地址
export QIDIAN_SAVE_URL='https://your-server.com'
export QIDIAN_SAVE_TOKEN='your-token'

# 搜索书籍
qidian-save search 仙侠

# 备份书籍
qidian-save backup 12345678 --start 1 --end 50
```

## API 集成

商业用户可使用 API Key 集成到自己项目:

```python
from qidian_save import QidianSaveClient

client = QidianSaveClient(
    "https://your-server.com",
    api_key="your-api-key"
)
books = client.search_books("玄幻")
```

详细 API 文档见 [docs/api.md](docs/api.md)。
