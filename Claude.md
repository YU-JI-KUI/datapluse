## 前端 Select 组件使用规范

**禁止在 SelectItem 的 value 属性中使用空字符串**

- **原因**：Radix UI Select 组件要求 SelectItem 的 value 必须是非空字符串，否则会抛出 "Select.Item must have a value prop that is not an empty string" 错误
- **解决方案**：
  - 使用有意义的字符串值，如 `'all'`、`'none'`、`'default'` 等
  - 在 API 调用时将特殊值转换为 `undefined` 或适当的默认值
  - 避免使用 `value=""` 作为默认状态

**示例错误代码**：
```jsx
<SelectItem value="">全部状态</SelectItem>  // ❌ 错误
```

**正确代码**：
```jsx
<SelectItem value="all">全部状态</SelectItem>  // ✅ 正确
// API 调用时：status === 'all' ? undefined : status
```

## 后端分页 API 响应结构规范

**分页接口统一使用 `page_data()` 封装，返回结构如下：**

```json
{
  "code": 0,
  "data": {
    "list": [...],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 100
    }
  }
}
```

**前端解析时必须使用 `list` 和 `pagination.total`，禁止使用 `items` 或顶层 `total`：**

```js
// axios response: res.data = { code, data: { list, pagination } }
const result = data?.data?.data ?? {}      // ✅ 取 data.data
const items  = result.list || []           // ✅ 正确
const total  = result.pagination?.total || 0  // ✅ 正确

// ❌ 错误写法（字段不存在，永远为空）
const items = result.items || []    // ❌ 后端返回 list 不是 items
const total = result.total || 0     // ❌ total 在 pagination 里
```

**受影响的所有分页查询（已修复）：** DataUpload、DataExplorer、Annotation（已标注面板）、PreAnnotation

## 后端 DataItem 响应字段规范

**`_item_to_dict` 和 `_enrich` 的返回字段必须与前端保持一致，禁止自造字段名。**

### 状态字段：统一用 `status`，不用 `stage`

```python
# ❌ 错误：前端读 item.status，返回 stage 导致状态永远为空
return { "stage": stage, ... }

# ✅ 正确：同时返回 status（前端用）和 stage（兼容导出模板）
return { "status": stage, "stage": stage, ... }
```

### 预标注字段：返回嵌套对象 `pre_annotation`，同时保留平铺字段供导出

```python
# ❌ 错误：前端读 item.pre_annotation.label，平铺字段不可见
base["model_pred"]  = pre.label if pre else None

# ✅ 正确：同时返回嵌套（前端列表用）和平铺（导出模板用）
base["model_pred"]  = pre.label if pre else None      # 导出模板用
base["model_score"] = float(pre.score) ...             # 导出模板用
base["pre_annotation"] = { "label": ..., "score": ..., "model_name": ... } if pre else None
```

### annotations 数组必须包含 `is_active` 字段

```python
# ❌ 错误：前端用 annList.find(a => a.is_active) 过滤，缺字段永远返回 undefined
{ "id": a.id, "label": a.label }

# ✅ 正确：_enrich 只查 is_active=True 的行，须在 dict 中显式声明
{ "id": a.id, "label": a.label, "is_active": True, ... }
```

**受影响页面（已修复）：** DataUpload、DataExplorer、PreAnnotation、Annotation

---

## 表格日期列必须防止换行

**所有表格中的日期/时间列（创建时间、更新时间、检测时间等）必须加 `whitespace-nowrap`，并给 TableHead 设置最小宽度 `w-40`，否则时间字符串会在列宽不足时自动换行，影响可读性。**

```jsx
// ❌ 错误：没有 whitespace-nowrap，时间容易换行
<TableHead>创建时间</TableHead>
<TableCell className="text-xs text-muted-foreground">{formatDate(item.created_at)}</TableCell>

// ✅ 正确
<TableHead className="w-40 whitespace-nowrap">创建时间</TableHead>
<TableCell className="text-xs text-muted-foreground whitespace-nowrap">{formatDate(item.created_at)}</TableCell>
```

**受影响的所有页面（已修复）：** DataUpload、DataManagement、DataExplorer、PreAnnotation、Annotation（已标注面板）、ConflictDetection

---

## 评论字段：后端返回 `comment`，前端不得读 `content`

**评论 API（`commentApi.list`）返回的字段名是 `comment`（与 `DataComment` 实体一致），不是 `content`。**

```js
// ❌ 错误：字段不存在，显示空白
<p>{c.content}</p>

// ✅ 正确
<p>{c.comment}</p>
```

---

## 标注结果架构：t_annotation vs t_annotation_result

**两张表职责严格分离，禁止混用：**

| 表 | 职责 | 谁写 | 是否可修改 |
|---|---|---|---|
| `t_annotation` | 标注事实（每人每版本） | 标注员 submit / revoke | 只能由标注员本人撤销 |
| `t_annotation_result` | 最终标注结果（每条数据一行） | 自动触发 / 冲突裁决 | 可被覆盖 |

**写入流程：**

```
标注员 submit/revoke
  → annotation_repository.create_annotation / revoke_annotation
  → _recompute_result()       ← 多数投票，更新 t_annotation_result（label_source='auto'）

冲突裁决
  → annotation_repository.set_manual_result()  ← 直接设置，label_source='manual'
  注意：不修改 t_annotation，标注事实保持不变
```

**DataExplorer 看到的 `label` 字段 = `t_annotation_result.final_label`**（非单个标注员标签）

**冲突裁决禁止调用 `force_set_annotation`**，只能调用 `set_annotation_result_manual`：

```python
# ❌ 错误：裁决时修改 t_annotation 事实
db.force_set_annotation(data_id, username, label)

# ✅ 正确：裁决时只更新 t_annotation_result
db.set_annotation_result_manual(data_id, final_label=label, resolver=username)
```

**标注工作台 API：`GET /api/annotations/my-items`**

- `view=all` — 全部条目（含已标注和未标注）
- `view=unannotated` — 当前用户未标注的
- `view=my_annotated` — 当前用户已标注的
- 每条记录含 `my_annotation` 字段（后端按当前用户过滤，前端无需再过滤）

**撤销标注只能撤销自己的**：前端读 `item.my_annotation`，后端 `revoke_annotation` 按 username 过滤，互不干扰。

---

## UI 提示/确认规范

**禁止使用浏览器原生 `alert()` / `confirm()` 进行提示或确认**

- 所有提示消息应统一使用站点风格的 toast 组件
- 所有确认操作应使用统一的对话框组件，而不是浏览器原生弹窗
- 这样可保证交互风格一致、可定制样式，并避免浏览器默认样式突兀

**示例规范**：
```js
toast.success('操作成功')

<ConfirmDialog
  open={open}
  onOpenChange={setOpen}
  title="确认删除"
  description="此操作不可撤销"
  onConfirm={handleDelete}
/>
```

## Tailwind 颜色变量必须在 tailwind.config.js 中注册

**下拉框（Select/Popover/Dropdown）内容透明、与背景内容重叠 → Root Cause：`popover` 颜色未在 Tailwind 配置中注册**

shadcn/ui 的 `SelectContent`、`PopoverContent` 等组件使用 `bg-popover` 和 `text-popover-foreground` Tailwind 类来设置背景色。如果 `tailwind.config.js` 的 `theme.extend.colors` 中缺少 `popover` 定义，这些 class 不会生成任何 CSS，导致背景透明，下拉框内容与页面内容重叠。

**必须在 `tailwind.config.js` 中注册所有 shadcn/ui 使用的颜色 token：**

```js
// tailwind.config.js — theme.extend.colors 必须包含：
colors: {
  border:      'hsl(var(--border))',
  input:       'hsl(var(--input))',
  ring:        'hsl(var(--ring))',
  background:  'hsl(var(--background))',
  foreground:  'hsl(var(--foreground))',
  primary:     { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
  secondary:   { DEFAULT: 'hsl(var(--secondary))', foreground: 'hsl(var(--secondary-foreground))' },
  destructive: { DEFAULT: 'hsl(var(--destructive))', foreground: 'hsl(var(--destructive-foreground))' },
  muted:       { DEFAULT: 'hsl(var(--muted))', foreground: 'hsl(var(--muted-foreground))' },
  accent:      { DEFAULT: 'hsl(var(--accent))', foreground: 'hsl(var(--accent-foreground))' },
  popover:     { DEFAULT: 'hsl(var(--popover))', foreground: 'hsl(var(--popover-foreground))' },  // ← 必须有！
  card:        { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--card-foreground))' },
}
```

CSS 变量本身在 `index.css` 的 `:root` 中定义，但 **必须同时** 在 tailwind.config.js 中注册为颜色 token，否则 `bg-popover` 等类名完全无效。
