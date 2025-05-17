import os
import re

def fix_log_statements(directory):
    # تمام .py فائلوں کو تلاش کریں
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # چیک کریں کہ logger درآمد ہے یا نہیں
                if 'from utils.logger import logger' not in content:
                    content = 'from utils.logger import logger\n' + content

                # log کو logger.error یا logger.warning سے بدلیں
                content = re.sub(r'\blog\.error\(', 'logger.error(', content)
                content = re.sub(r'\blog\.warning\(', 'logger.warning(', content)
                content = re.sub(r'\blog\.info\(', 'logger.info(', content)
                content = re.sub(r'\blog\(', 'logger.error(', content)  # عمومی log کو logger.error سے بدلیں

                # اپ ڈیٹ شدہ فائل لکھیں
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"Fixed {file_path}")

if __name__ == '__main__':
    project_dir = '.'  # پروجیکٹ کی روٹ ڈائریکٹری
    fix_log_statements(project_dir)
