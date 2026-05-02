import sys, traceback
sys.path.insert(0, 'src')

# 先看实际用的路径
from datapulse.config.settings import get_settings
path = get_settings().embedding_model_path
print('=== model_path ===', path)

# 看路径下有什么文件
import os
if os.path.exists(path):
    for f in os.listdir(path):
        size = os.path.getsize(os.path.join(path, f))
        print(f'  {f}  {size:,} bytes')
else:
    print('  !! 路径不存在 !!')

# 尝试加载，打完整堆栈
print()
print('=== 尝试加载 ===')
try:
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(path, local_files_only=True)
    print('OK, dim =', m.get_embedding_dimension())
except Exception:
    traceback.print_exc()