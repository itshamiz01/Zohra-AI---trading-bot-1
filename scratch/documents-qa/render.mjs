import fs from 'node:fs/promises';
import {FileBlob, SpreadsheetFile} from '@oai/artifact-tool';

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(process.argv[2]));
const sheet = workbook.worksheets.getItem('Data');
if (sheet.getRange('B3').values[0][0] !== '=1+2') throw new Error('Literal formula text changed on import');
console.log((await workbook.inspect({kind:'table',range:'Data!A1:C4',include:'values,formulas',tableMaxRows:4,tableMaxCols:3,maxChars:3000})).ndjson);
const image = await workbook.render({sheetName:'Data',range:'A1:C4',scale:2,format:'png'});
await fs.writeFile(process.argv[3],new Uint8Array(await image.arrayBuffer()));
console.log('Spreadsheet preview saved');
