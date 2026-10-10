import sys,json,pandas as pd,geopandas as gpd
from shapely.geometry import LineString, box
G,O=sys.argv[1:]
B=box(152.80,-27.62,153.12,-27.33)
r=pd.read_csv(f"{G}/routes.txt",dtype=str); t=pd.read_csv(f"{G}/trips.txt",dtype=str,usecols=['route_id','shape_id'])
t=t.drop_duplicates('shape_id').merge(r[['route_id','route_type']],on='route_id')
keep=set(t.shape_id); parts=[]
for ch in pd.read_csv(f"{G}/shapes.txt",dtype={'shape_id':str,'shape_pt_lat':'float32','shape_pt_lon':'float32','shape_pt_sequence':'int32'},usecols=['shape_id','shape_pt_lat','shape_pt_lon','shape_pt_sequence'],chunksize=500_000):
    ch=ch[(ch.shape_pt_lon.between(152.75,153.15))&(ch.shape_pt_lat.between(-27.65,-27.30))&ch.shape_id.isin(keep)]
    parts.append(ch)
sh=pd.concat(parts).sort_values(['shape_id','shape_pt_sequence']); del parts
print(len(sh),flush=True)
rows=[(k,LineString(list(zip(v.shape_pt_lon.astype(float),v.shape_pt_lat.astype(float))))) for k,v in sh.groupby('shape_id') if len(v)>1]
del sh
g=gpd.GeoDataFrame(rows,columns=['shape_id','geometry'],crs=4326).merge(t[['shape_id','route_type']],on='shape_id').to_crs(7856)
g['geometry']=g.simplify(10)
print(g.route_type.value_counts())
BB=gpd.GeoSeries([B],crs=4326).to_crs(7856).iloc[0]
def rnd(o): return [rnd(x) for x in o] if isinstance(o,(list,tuple)) else (round(o,4) if isinstance(o,float) else o)
out={}
for typ,key,tol in [('3','roads',12),('2','rail',15),('4','river',20)]:
    u=g[g.route_type==typ].geometry.union_all().intersection(BB).simplify(tol)
    js=json.loads(gpd.GeoSeries([u],crs=7856).to_crs(4326).to_json())['features'][0]['geometry']
    js['coordinates']=rnd(js['coordinates']); out[key]=js
json.dump(out,open(f"{O}/base.json","w"),separators=(',',':'))
m=json.load(open(f"{O}/meta.json")); hs=m['hubs']
if len(hs)>1:
    agg={};rs=set()
    for h in hs:
        for k,v in h['groups'].items(): agg[k]=agg.get(k,0)+v
        rs|=set(h['routes'])
    m['hubs']=[dict(name="UQ Chancellors Place",lat=hs[0]['lat'],lon=hs[0]['lon'],groups=agg,routes=sorted(rs,key=lambda x:(len(x),x)))]
    json.dump(m,open(f"{O}/meta.json","w"),indent=1)
print(m['hubs'])
