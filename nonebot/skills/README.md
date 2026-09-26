# 服务器本地聊天 Skill

这里的 Skill 是纯文本聊天能力包，不是 OpenAI 网页版工具，也不会执行目录里的代码。每个一级子目录必须包含：

- `skill.toml`：ID、名称、说明、触发词与可用场景。
- `SKILL.md`：被选中后加入模型上下文的规则。

最小示例：

```toml
id = "example_support"
name = "产品答疑"
description = "根据维护者提供的产品规则回答问题"
enabled = true
always = false
triggers = ["产品", "售后"]
contexts = ["private", "group"]
```

Loader 只读取一级目录中的上述两个文件，拒绝符号链接、非法 ID、空文件与超大文件。一个 Skill 损坏不会阻止机器人启动。

## 安全边界

- Skill 只能补充语义、流程和回复规范，不能覆盖核心安全规则。
- Skill 目录不得包含 Token、Cookie、密码、真实 `.env` 或其他 Secret。
- 纯文本 Skill 不等于外部查询已经执行；没有程序提供的已验证结果时，模型不得声称查询成功。
- 如果要连接第三方 API，请另外实现固定的异步 service，再由独立 plugin 调用。固定 Origin、方法和参数结构，设置 timeout，严格校验响应，并在请求前完成权限检查。
- 禁止通用 HTTP 代理、用户可控 URL、Shell、subprocess、`eval`、`exec` 或动态加载 Skill 代码。

完整开发方式见 `docs/DEVELOPMENT.md`。
