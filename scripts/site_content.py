"""Editable public copy. Plain text only; the static application owns markup."""
import json
from pathlib import Path

PAGES = {
    'index': ('进度概览', '当前 Demo 阶段的整体完成度、评估时间与发布状态。'),
    'dimensions': ('维度进度', '剧情、美术与场景、系统和打磨的完成度、权重与主要剩余内容。'),
    'updates': ('最近更新', '本次评估的主要成果、变化原因与提交基线。'),
    'todos': ('Todo 清单', '按维度、状态和范围查看任务及完成条件。'),
    'history': ('历史记录', '查看完成度趋势与各次评估的范围、规则和结果。'),
    'method': ('计算说明', '完成度计算规则、手动评分与验收要求。'),
}
DEFAULT = {'schema_version': '1.0.0', 'pages': {k: {'title': v[0], 'intro': v[1]} for k,v in PAGES.items()}, 'text': {
    'dimensions-title':'维度完成度','updates-title':'本次评估','todos-title':'任务列表','history-title':'趋势与评估记录','method-title':'评分规则',
    'method-weight-title':'按目标与权重计算','method-status-title':'状态与验收',
    'method-weight-note':'只计算 Demo 范围内的最末层任务，父项只汇总；任务细化保持原预算。范围扩大或规则改变时，记录原因并保留过去的口径。',
    'method-status-note':'未知状态保持待确认。功能分支已有实现单独记录，主分支集成后才能确认 Demo 中可用。UI 与打磨由开发者分别评分。',
    'method-limit-note':'静态检查不能替代游戏运行、视觉或听觉验收。百分比不预测剩余工时，也不自动代表发布就绪。',
    'todo-note':'任务数量仅供浏览参考，完成度按相对权重计算。展开大项可查看必要子项。已完成的大项和子项排在各自列表末尾。',
    'empty':'此筛选下没有任务。可以切换维度、状态或查看范围。',
    'loading':'正在读取进度数据…','error-title':'进度数据加载失败','retry':'重新读取数据',
    'footer-note':'Todo 驱动的开发进度记录','method-note':'依据静态评估与开发者验收记录 · 不代表工期',
}}

def validate_content(content):
    if not isinstance(content, dict) or set(content) != set(DEFAULT) or content['schema_version'] != '1.0.0':
        raise ValueError('网站文案格式无效')
    if not isinstance(content['pages'],dict) or set(content['pages']) != set(PAGES):
        raise ValueError('网站文案必须包含六个页面')
    for page in content['pages'].values():
        if not isinstance(page,dict) or set(page) != {'title','intro'}:
            raise ValueError('页面文案字段无效')
        for value in page.values():
            if not isinstance(value,str) or not value.strip() or len(value)>10000:
                raise ValueError('页面标题和介绍必须为非空纯文本（最多10000字）')
    if not isinstance(content['text'],dict) or set(content['text']) != set(DEFAULT['text']):
        raise ValueError('提示文案字段无效')
    if any(not isinstance(v,str) or not v.strip() or len(v)>10000 for v in content['text'].values()):
        raise ValueError('提示文案必须为非空纯文本（最多10000字）')
    return content

def load_content(project):
    path=Path(project)/'site.content.json'
    return validate_content(json.loads(path.read_text(encoding='utf-8')) if path.exists() else json.loads(json.dumps(DEFAULT)))
