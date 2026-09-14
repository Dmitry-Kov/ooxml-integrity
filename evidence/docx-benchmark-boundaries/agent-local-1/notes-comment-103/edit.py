from docx import Document

def replace_sentence_in_comment(input_path, output_path):
    doc = Document(input_path)
    
    for paragraph in doc.paragraphs:
        if len(paragraph.comments) > 0 and paragraph._element.tag.endswith('p'):
            comment = paragraph.comments[0]
            if 'Review the delivery terms.' in comment.text:
                new_text = comment.text.replace('delivery', 'payment')
                comment.text = new_text
                break
    
    doc.save(output_path)

try:
    replace_sentence_in_comment('input.docx', 'output.docx')
except Exception as e:
    raise Exception(f"Failed to perform the task: {e}")
