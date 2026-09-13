from docx import Document

def copy_docx(input_path, output_path):
    try:
        # Load the input document
        doc = Document(input_path)
        
        # Save the document to the output path
        doc.save(output_path)
        
        print(f"Document copied from {input_path} to {output_path}")
    
    except Exception as e:
        raise Exception(f"Failed to copy document: {e}")

# Example usage
copy_docx('input.docx', 'output.docx')
