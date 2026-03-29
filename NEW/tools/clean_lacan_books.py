#!/usr/bin/env python3
"""清理拉康书籍中的页码标记和页眉 - 逐本处理"""

import re
from pathlib import Path

def clean_拉康选集(content: str) -> str:
    """清理《拉康选集》的页码、页眉和脚注"""

    # 第一步：清理脚注（整体正则匹配）
    # 使用 DOTALL 让 . 匹配换行符，实现跨行匹配

    # 模式1：行首 ①②③... 开头，到 (译者注) 或 (原注) 结尾
    # 必须是行首，避免删除正文中的脚注引用标记
    footnote_pattern1 = r'^\s*[①②③④⑤⑥⑦⑧⑨⑩].*?\((?:译者注|原注)\)'
    content = re.sub(footnote_pattern1, '', content, flags=re.MULTILINE | re.DOTALL)

    # 模式2：行首 ** 或 * 开头的脚注（少数情况）
    footnote_pattern2 = r'^\s*\*+[^①②③④⑤⑥⑦⑧⑨⑩\n].*?\((?:译者注|原注)\)'
    content = re.sub(footnote_pattern2, '', content, flags=re.MULTILINE | re.DOTALL)

    # 第三步：删除正文中的脚注引用标记（①②③等）
    content = re.sub(r'[①②③④⑤⑥⑦⑧⑨⑩]', '', content)

    # 第四步：逐行清理页码和页眉
    lines = content.split('\n')
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()

        # 跳过页码行: --- Page XX ---
        if re.match(r'^---\s*Page\s*\d+\s*---$', stripped):
            continue

        # 跳过页眉: "数字 拉康选集"
        if re.match(r'^\d+\s+拉康选集$', stripped):
            continue

        # 跳过页眉: "章节名 页码" (各种章节)
        # 已知章节名列表
        chapters = [
            r'关于《.+》的研讨会',
            '超越["""\u201c\u201d]现实原则["""\u201c\u201d]',
            r'典型疗法的变体',
            r'弗洛伊德事务或在精神分析学中回归弗洛伊德的意义',
            r'关于我的经历',
            r'精神分析学在犯罪学中的功能的理论导论',
            r'精神分析学中的言语和语言的作用和领域',
            r'精神分析中的侵凌性',
            r'就转移作的发言',
            r'论精神错乱的.?切可能疗法的一个先决问题',
            r'逻辑时间及预期确定性的肯定',
            r'男根的意义',
            r'谈心理因果',
            r'无意识中文字的动因或自弗洛伊德以来的理性',
            r'译名对照表',
            r'治疗的方向和它的力量的原则',
            r'终于谈到了主体',
            r'主体的倾覆和在弗洛伊德无意识中的欲望的辩证法',
            '助成["""\u201c\u201d]我["""\u201c\u201d]的功能形成的镜子阶段',
        ]
        is_chapter_header = any(
            re.match(rf'^{ch}\s+\d{{1,3}}$', stripped) for ch in chapters
        )
        if is_chapter_header:
            continue

        cleaned_lines.append(line)

    # 合并多个连续空行为单个空行
    result = '\n'.join(cleaned_lines)
    # 先将只含空白字符的行变成空行
    result = re.sub(r'^[ \t]+$', '', result, flags=re.MULTILINE)
    # 再合并连续空行
    result = re.sub(r'\n{2,}', '\n', result)

    return result.strip()

def clean_研讨班02(content: str) -> str:
    """清理《研讨班02-自我》的页码和页眉"""
    lines = content.split('\n')
    cleaned_lines = []

    # 英文页眉列表（出现多次的都是页眉）
    english_headers = [
        'Psychology and metapsychology',
        'Homeostasis and insistence',
        'Psychoanalysis and cybernetics, or on the nature of language',
        'The dream of Irma\'s injection',
        'A, m, a, S',
        'The purloined letter',
        'WHERE IS SPEECH? WHERE IS LANGUAGE?',
        'Odd or even? Beyond intersubjectivity',
        'Some questions for the teacher',
        'Desire, life and death',
        'Sosie184F',
        'Introduction of the big Other',
        'The circuit',
        'Knowledge, truth, opinion',
        'A materialist definition of the phenomenon of consciousness',
        'The symbolic universe',
        'Freud, Hegel and the machine',
        'The difficulties of regression',
        'Play of writings',
        'Objectified analysis',
        'Censorship is not resistance',
        'Introduction to the Entwurf',
        'From the Entwurf to the Traumdeutung',
    ]
    # 中文页眉列表
    chinese_headers = [
        '精神分析与元心理学',
        '恒定与坚持',
        '精神分析与控制论，或论语言的本质',
        '大他者，自我，小他者，主体',
        '失窃的信',
        '言说在哪？语言在哪？',
        '奇数还是偶数？超越主体间性',
        '欲望，生命与死亡',
        '伊玛打针之梦',
        '一些给教学者的问题',
        '索西亚斯',
        '精神分析与控制论，或关于语言的本质',
        '大他者导论',
        '知识、真理、观点',
        '循环',
        '对意识现象的唯物主义定义',
        '象征宇宙',
        '弗洛伊德，黑格尔和机器',
        '关于退行的争议',
        '书写的游戏',
        '伊玛打针之梦（结论）',
        '稳态与坚持',
        '客体化分析',
        '(conclusion)',
        '审查并非阻抗',
        '从《大纲》到《梦的解析》',
        '《（科学心理学）大纲》导论',
    ]

    # 删除正文中的脚注引用数字（如 "式21，" → "式，"）
    # 匹配：中文字符后的数字，后面跟标点
    content = re.sub(r'([\u4e00-\u9fff])(\d{1,3})([，。、）])', r'\1\3', content)

    lines = content.split('\n')
    in_footnote = False  # 追踪是否在脚注中

    for line in lines:
        stripped = line.strip()

        # 跳过页码行: - 1 -
        if re.match(r'^- \d+ -$', stripped):
            in_footnote = False  # 页码后脚注结束
            continue

        # 跳过罗马数字章节标记（如 I, II, XVI, XXIV）
        if re.match(r'^[IVXLC]+$', stripped):
            in_footnote = False  # 章节标记后脚注结束
            continue

        # 跳过阿拉伯数字页码（如 1, 27）
        if re.match(r'^\d+$', stripped):
            continue

        # 检测脚注开始（如 "21 格式塔心理学..."）
        if re.match(r'^\d+ \S', stripped):
            in_footnote = True
            continue

        # 如果在脚注中，继续跳过直到脚注结束
        if in_footnote:
            # 空行不结束脚注
            if not stripped:
                continue
            # 如果是页眉，结束脚注
            if stripped in english_headers or stripped in chinese_headers:
                in_footnote = False
            else:
                # 继续跳过脚注内容
                continue

        # 跳过以（译注）结尾的行（脚注尾部）
        if stripped.endswith('（译注）'):
            continue

        # 跳过英文页眉
        if stripped in english_headers:
            continue

        # 跳过中文页眉
        if stripped in chinese_headers:
            continue

        cleaned_lines.append(line)

    # 合并多个连续空行为单个空行
    result = '\n'.join(cleaned_lines)
    # 先将只含空白字符的行变成空行
    result = re.sub(r'^[ \t]+$', '', result, flags=re.MULTILINE)
    # 再合并连续空行
    result = re.sub(r'\n{2,}', '\n', result)

    return result.strip()

def clean_研讨班07(content: str) -> str:
    """清理《研讨班07-精神分析的伦理学》的页码、页眉和脚注"""

    # 第一步：清理脚注
    # 格式：① 开头，以 ——译注 或 ————译注 结尾
    footnote_pattern = r'^\s*[①②③④⑤⑥⑦⑧⑨⑩].*?——+译注'
    content = re.sub(footnote_pattern, '', content, flags=re.MULTILINE | re.DOTALL)

    # 删除正文中的脚注引用标记（①②③等）
    content = re.sub(r'[①②③④⑤⑥⑦⑧⑨⑩]', '', content)

    # 删除行末混入的页码（如 "...的那些人。 94" 或 "...而言,232"）
    content = re.sub(r'[,，\s]\d{1,3}$', lambda m: m.group(0)[0] if m.group(0)[0] in ',，' else '', content, flags=re.MULTILINE)

    # 删除行首混入的页码（如 "231 这里涉及的..." → "这里涉及的..."）
    content = re.sub(r'^\d{1,3} ', '', content, flags=re.MULTILINE)

    # 逐行清理页码和页眉
    lines = content.split('\n')
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()

        # 跳过页码行: --- Page XX ---
        if re.match(r'^---\s*Page\s*\d+\s*---$', stripped):
            continue

        # 跳过页眉: "第X讲XXX 数字" 或 "数字 第X讲XXX"
        if re.match(r'^第.+讲.+\s+\d{1,3}$', stripped):
            continue
        if re.match(r'^\d{1,3}\s+第.+讲', stripped):
            continue

        # 跳过页眉: "数字 部分标题"
        section_titles = [
            r'["\u201c]物["\u201d]的引论',
            r'升华的问题',
            r'享受的悖论',
            r'悲剧的本质',
            r'精神分析经验的悲剧维度',
        ]
        is_section_header = any(
            re.match(rf'^\d{{1,3}}\s*{title}$', stripped) for title in section_titles
        )
        if is_section_header:
            continue

        # 跳过独立的部分标题
        is_standalone_title = any(
            re.match(rf'^{title}$', stripped) for title in section_titles
        )
        if is_standalone_title:
            continue

        # 跳过单独的数字（页码）
        if re.match(r'^\d+$', stripped):
            continue

        # 跳过单独的 "译注" 行（脚注残留）
        if stripped == '译注':
            continue

        cleaned_lines.append(line)

    # 合并多个连续空行为单个空行
    result = '\n'.join(cleaned_lines)
    # 先将只含空白字符的行变成空行
    result = re.sub(r'^[ \t]+$', '', result, flags=re.MULTILINE)
    # 再合并连续空行
    result = re.sub(r'\n{2,}', '\n', result)

    return result.strip()

def process_file(filepath: Path, clean_func):
    """处理单个文件"""
    print(f"处理: {filepath.name}")

    content = filepath.read_text(encoding='utf-8')
    original_lines = len(content.split('\n'))

    cleaned = clean_func(content)
    cleaned_lines = len(cleaned.split('\n'))

    # 备份原文件
    backup_path = filepath.with_suffix('.txt.bak')
    if not backup_path.exists():
        import shutil
        shutil.copy(filepath, backup_path)
        print(f"  备份: {backup_path.name}")

    # 写入清理后的文件
    filepath.write_text(cleaned, encoding='utf-8')

    print(f"  原始: {original_lines} 行 -> 清理后: {cleaned_lines} 行")
    print("  完成!")

def main():
    # 处理研讨班07
    book = Path("lifee/roles/lacan/knowledge/books/研讨班07-精神分析的伦理学.txt")

    if not book.exists():
        print(f"文件不存在: {book}")
        return

    process_file(book, clean_研讨班07)

if __name__ == "__main__":
    main()
