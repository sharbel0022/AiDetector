"""Literal text comparison without HTML rendering."""
from difflib import SequenceMatcher
import re

def make_diff(original: str, rewritten: str) -> list[dict]:
    a=re.findall(r'\s+|\w+|[^\w\s]',original)
    b=re.findall(r'\s+|\w+|[^\w\s]',rewritten)
    result=[]
    for tag,i,j,k,l in SequenceMatcher(None,a,b,autojunk=True).get_opcodes():
        if tag=='equal':result.append({'kind':'equal','text':''.join(b[k:l])})
        else:
            if tag in ('delete','replace'):result.append({'kind':'delete','text':''.join(a[i:j])})
            if tag in ('insert','replace'):result.append({'kind':'insert','text':''.join(b[k:l])})
    return result
