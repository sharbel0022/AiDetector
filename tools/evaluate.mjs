import fs from 'node:fs';
import { pathToFileURL } from 'node:url';
import { analyzeText } from '../sites/src/analyzer.mjs';
const ratio=(a,b)=>b?a/b:null;
export function summarize(rows,threshold=65){
  if(!Number.isFinite(threshold)||threshold<0||threshold>100)throw new Error('Threshold must be 0–100');
  const confusion={tp:0,fp:0,tn:0,fn:0};let abstained=0,totalAI=0;
  for(const row of rows){
    if(!['human','ai'].includes(row.label))throw new Error('Each label must be human or ai');
    if(row.label==='ai')totalAI++;
    if(row.score===null){abstained++;continue;}
    if(!Number.isFinite(row.score)||row.score<0||row.score>100)throw new Error('Invalid style index');
    const positive=row.score>=threshold;
    confusion[row.label==='ai'?(positive?'tp':'fn'):(positive?'fp':'tn')]++;
  }
  const {tp,fp,tn,fn}=confusion,assessed=rows.length-abstained;
  return {total:rows.length,assessed,abstained,threshold,coverage:ratio(assessed,rows.length),confusion,accuracyAssessed:ratio(tp+tn,assessed),precision:ratio(tp,tp+fp),recallAssessed:ratio(tp,tp+fn),recallAllAI:ratio(tp,totalAI),falsePositiveRate:ratio(fp,fp+tn),f1:ratio(2*tp,2*tp+fp+fn)};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{
    const file=process.argv[2];
    if(!file)throw new Error('Usage: npm run evaluate -- dataset.jsonl [threshold]');
    if(fs.statSync(file).size>10_000_000)throw new Error('Dataset exceeds 10 MB');
    const seen=new Set();
    const rows=fs.readFileSync(file,'utf8').split(/\r?\n/).filter(x=>x.trim()).map((line,index)=>{
      const r=JSON.parse(line);
      if(typeof r.source_id!=='string'||!r.source_id||seen.has(r.source_id))throw new Error(`Missing or duplicate source_id on line ${index+1}`);
      if(!['sv','en'].includes(r.language))throw new Error(`Unsupported language on line ${index+1}`);
      seen.add(r.source_id);
      return {label:r.label,language:r.language,score:analyzeText(r.text,r.language).styleIndex};
    });
    if(!rows.length)throw new Error('Dataset is empty');
    const threshold=process.argv[3]===undefined?65:Number(process.argv[3]);
    console.log(JSON.stringify({method:'style-heuristics-v2',notice:'Evaluation of a fixed style threshold, not a calibrated authorship probability. Independently verify labels and do not tune this threshold on the test split.',overall:summarize(rows,threshold),byLanguage:Object.fromEntries(['sv','en'].map(l=>[l,summarize(rows.filter(r=>r.language===l),threshold)]))},null,2));
  }catch(error){console.error(error.message);process.exitCode=1;}
}
