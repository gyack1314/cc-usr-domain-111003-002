def project(rows,fields):
    if len(fields)!=len(set(fields)):raise ValueError('字段重复')
    return [{k:r[k] for k in fields} for r in rows]
def group_sizes(rows,keys,person_key):
    groups={}
    for r in rows:
        key=tuple(r[k] for k in keys);groups.setdefault(key,set()).add(r[person_key])
    return [{'key':list(k),'people':len(v)} for k,v in sorted(groups.items())]
def lineage(rows,source_key):
    return sorted({r[source_key] for r in rows})
TOOLS={'project':project,'group_sizes':group_sizes,'lineage':lineage}
