# Release 标题规范

所有 GitHub Release 标题统一使用仓库名和版本号：

```text
octop-social-trigger vX.Y.Z
```

`X.Y.Z` 必须与 Git tag 和插件版本完全一致。例如发布 `v0.3.4` 时，标题写作 `octop-social-trigger v0.3.4`。不要使用裸版本号或其他标题变体。

创建 Release 时显式传入标题，避免 GitHub 默认使用 tag 名：

```sh
gh release create v0.3.4 \
  --title "octop-social-trigger v0.3.4" \
  --verify-tag \
  --notes-file release-notes.md \
  dist/octop-social-trigger-0.3.4.zip \
  dist/SHA256SUMS
```

已发布的历史 Release 也统一为此格式；调整标题不改变 tag、发布说明或附件。
