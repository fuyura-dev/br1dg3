import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

// Setup for ES Modules
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const componentsDir = path.join(__dirname, 'src', 'components', 'accessibility-studio');
const stylesDir = path.join(__dirname, 'src', 'styles');

// Create the new centralized styles directory
if (!fs.existsSync(stylesDir)) {
  fs.mkdirSync(stylesDir, { recursive: true });
}

fs.readdirSync(componentsDir).forEach(file => {
  const oldPath = path.join(componentsDir, file);

  if (file.endsWith('.css')) {
    // Move the CSS file
    const newPath = path.join(stylesDir, file);
    fs.renameSync(oldPath, newPath);
    console.log(`Moved: ${file} -> src/styles/`);
  } else if (file.endsWith('.jsx')) {
    // Update the import statements in the JSX file
    let content = fs.readFileSync(oldPath, 'utf8');
    
    // Finds: import './SomeFile.css' and replaces with: import '../../styles/SomeFile.css'
    const updatedContent = content.replace(/import\s+['"]\.\/(.*?\.css)['"]/g, "import '../../styles/$1'");
    
    if (content !== updatedContent) {
      fs.writeFileSync(oldPath, updatedContent, 'utf8');
      console.log(`Updated imports in: ${file}`);
    }
  }
});

console.log('CSS Restructuring Complete. You can now delete this script.');