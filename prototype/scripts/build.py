import sys, json, re, datetime as dt
import pandas as pd, geopandas as gpd, numpy as np
from shapely.geometry import LineString, Point, MultiPoint, box
from shapely.ops import unary_union, voronoi_diagram
G, OUT, LIST = sys.argv[1], sys.argv[2], sys.argv[3]
lines=open(LIST).read().splitlines()[1:]
want=sorted({re.match(r'(N?\d+)',l.strip()).group(1) for l in lines if l.strip()})
want=[w for w in want if not (w[0] in '79')]
r=pd.read_csv(f"{G}/routes.txt",dtype=str)
r=r[r.route_short_name.isin(want) & r.route_id.str.endswith('-5146')]
def grp(n):
    d=n.lstrip('N'); return d[:2]+'x'
r['group']=r.route_short_name.map(grp)
# representative weekday service
DAY=dt.date(2026,10,14); ds=DAY.strftime('%Y%m%d')
cal=pd.read_csv(f"{G}/calendar.txt",dtype=str)
act=set(cal[(cal.wednesday=='1')&(cal.start_date<=ds)&(cal.end_date>=ds)].service_id)
cd=pd.read_csv(f"{G}/calendar_dates.txt",dtype=str); cd=cd[cd.date==ds]
act|=set(cd[cd.exception_type=='1'].service_id); act-=set(cd[cd.exception_type=='2'].service_id)
t=pd.read_csv(f"{G}/trips.txt",dtype=str)
t=t[t.route_id.isin(r.route_id)]
t['active']=t.service_id.isin(act)
ta=t[t.active].merge(r[['route_id','route_short_name','group']],on='route_id')
print("weekday trips:",len(ta))
# stop_times for active trips
ids=set(ta.trip_id); parts=[]
for ch in pd.read_csv(f"{G}/stop_times.txt",dtype=str,usecols=['trip_id','stop_id','stop_sequence'],chunksize=2_000_000):
    parts.append(ch[ch.trip_id.isin(ids)])
st=pd.concat(parts).merge(ta[['trip_id','route_short_name','group']],on='trip_id')
stops=pd.read_csv(f"{G}/stops.txt",dtype=str)
stops[['stop_lat','stop_lon']]=stops[['stop_lat','stop_lon']].astype(float)
# shapes: most-used shape per route+direction (plus any shape >=15% of that route's trips)
sc=ta.groupby(['route_short_name','group','direction_id','shape_id']).size().reset_index(name='n')
tot=sc.groupby(['route_short_name','direction_id']).n.transform('sum')
sc['main']=(sc.n/tot>=0.15)
sh=pd.read_csv(f"{G}/shapes.txt",dtype={'shape_id':str})
sh=sh[sh.shape_id.isin(sc.shape_id)].sort_values(['shape_id','shape_pt_sequence'])
geom={k:LineString(list(zip(v.shape_pt_lon,v.shape_pt_lat))) for k,v in sh.groupby('shape_id')}
rt=sc.copy(); rt['geometry']=rt.shape_id.map(geom)
rt=gpd.GeoDataFrame(rt,crs=4326)
names=dict(zip(r.route_short_name,r.route_long_name))
rtrips=ta.groupby('route_short_name').size().to_dict()
rt['name']=rt.route_short_name.map(names); rt['trips']=rt.route_short_name.map(rtrips)
# stop -> group trip counts
sg=st.groupby(['stop_id','group']).size().unstack(fill_value=0)
srt=st.groupby('stop_id').route_short_name.agg(lambda s: sorted(set(s),key=lambda x:(len(x),x)))
S_=stops.set_index('stop_id').loc[sg.index]
# hubs
def hub(nm):
    n=nm.lower()
    if 'university of queensland' in n or 'uq lakes' in n or 'chancellors place' in n or 'uq ' in n: return 'UQ'
    return None
S_['hub']=S_.stop_name.map(hub)
gp=gpd.GeoDataFrame(S_[['stop_name','hub','parent_station']].copy(),geometry=gpd.points_from_xy(S_.stop_lon,S_.stop_lat),crs=4326).to_crs(7856)
sg=sg.astype(float); share=sg.div(sg.sum(1),axis=0)
gp['dom']=share.idxmax(1); gp['domshare']=share.max(1); gp['ntrips']=sg.sum(1)
gp['groups']=[ {k:int(v) for k,v in row.items() if v>0} for _,row in sg.iterrows()]
gp['routes']=srt
# CBD exclusion: within 1.6 km of Queen St Mall
cbd=gpd.GeoSeries([Point(153.0251,-27.4698)],crs=4326).to_crs(7856).iloc[0]
gp['cbd']=gp.distance(cbd)<1700
gp['cls']=np.where(gp.hub.notna(),'hub',np.where(gp.cbd,'cbd',np.where(gp.domshare>=0.6,gp.dom,'shared')))
# Voronoi catchments clipped to 400 m walk buffer
pts=gp.drop_duplicates(subset=gp.geometry.name) if False else gp
env=box(*pts.total_bounds).buffer(3000)
vor=voronoi_diagram(MultiPoint(list(pts.geometry)),envelope=env)
cells=gpd.GeoDataFrame(geometry=list(vor.geoms),crs=7856)
pp=pts[['cls','geometry']].reset_index(drop=True); pp['pid']=range(len(pp))
j=gpd.sjoin(cells,pp,predicate='contains',how='inner')
j['geometry']=[c.intersection(pp.geometry.iloc[i].buffer(400)) for c,i in zip(j.geometry,j.pid)]
R_=list(gp.routes); GR=list(gp.groups)
def pct(d):
    tot=sum(d.values()); return ' '.join(f"{k}:{round(100*v/tot)}" for k,v in sorted(d.items(),key=lambda x:-x[1]))
cells_out=j[['pid','cls','geometry']].copy()
cells_out['r']=[' '.join(R_[i]) for i in cells_out.pid]
cells_out['g']=[pct(GR[i]) for i in cells_out.pid]
cells_out['geometry']=cells_out.simplify(10)
zones=j.dissolve(by='cls').reset_index()[['cls','geometry']]
zones['geometry']=zones.buffer(30).buffer(-30).simplify(15)
# group stats
gs=[]
for g_,d in r.groupby('group'):
    rs=sorted(d.route_short_name,key=lambda x:(len(x),x))
    z=zones[zones.cls==g_]
    sub=gp[gp.cls==g_]
    top=sub.stop_name.str.extract(r',\s*([^,]+)$')[0].dropna()
    uq=int(sum(gp[gp.hub=='UQ'].groups.map(lambda x:x.get(g_,0))))
    gs.append(dict(group=g_,routes=rs,trips=int(sum(rtrips.get(x,0) for x in rs)),
        area_km2=round(float(z.area.sum())/1e6,1) if len(z) else 0,
        own_stops=int(len(sub)),uq_stop_visits=uq))
print(pd.DataFrame(gs).to_string())
print(gp.cls.value_counts().to_string())
def out(gdf,fn,prec=5):
    gdf=gdf.to_crs(4326)
    js=json.loads(gdf.to_json(drop_id=True))
    def rnd(o):
        if isinstance(o,float): return round(o,prec)
        if isinstance(o,list): return [rnd(x) for x in o]
        if isinstance(o,dict): return {k:rnd(v) for k,v in o.items()}
        return o
    json.dump(rnd(js),open(f"{OUT}/{fn}","w"),separators=(',',':'))
rt2=rt.to_crs(7856); rt2['geometry']=rt2.simplify(6)
out(rt2[['route_short_name','group','direction_id','name','trips','main','n','geometry']],'routes.geojson')
rp=rt.to_crs(7856); rb=[]; gb=[]
for rn,d in rp.groupby('route_short_name'):
    m=d[d.main].geometry.union_all().buffer(250); a=d.geometry.union_all().buffer(250); v=a.difference(m).buffer(-5).buffer(5)
    g_=d.group.iloc[0]; rb.append((rn,g_,'main',m))
    if not v.is_empty and v.area>20000: rb.append((rn,g_,'variant',v))
for g_,d in rp.groupby('group'):
    m=d[d.main].geometry.union_all().buffer(250); v=d.geometry.union_all().buffer(250).difference(m).buffer(-5).buffer(5)
    gb.append((g_,'main',m))
    if not v.is_empty and v.area>20000: gb.append((g_,'variant',v))
rbg=gpd.GeoDataFrame(rb,columns=['route','group','kind','geometry'],crs=7856); rbg['geometry']=rbg.simplify(15)
gbg=gpd.GeoDataFrame(gb,columns=['group','kind','geometry'],crs=7856); gbg['geometry']=gbg.simplify(15)
out(rbg,'routebuf.geojson'); out(gbg,'groupbuf.geojson')
out(zones,'zones.geojson')
out(cells_out[['cls','r','g','geometry']],'cells.geojson')
gpo=gp[['stop_name','cls','ntrips','routes','geometry']].copy(); gpo['routes']=gpo.routes.map(' '.join)
rc=st.groupby(['stop_id','route_short_name']).size()
def rcs(sid):
    d=rc.loc[sid]; return ' '.join(f"{k}:{int(v)}" for k,v in sorted(d.items(),key=lambda x:(len(x[0]),x[0])))
gpo['rc']=[rcs(i) for i in gpo.index]
# other routes (any operator) stopping here on the same weekday
tall=pd.read_csv(f"{G}/trips.txt",dtype=str,usecols=['route_id','service_id','trip_id'])
tall=tall[tall.service_id.isin(act)&~tall.route_id.isin(r.route_id)]
ra=pd.read_csv(f"{G}/routes.txt",dtype=str,usecols=['route_id','route_short_name'])
tall=tall.merge(ra,on='route_id'); tid=dict(zip(tall.trip_id,tall.route_short_name))
sset=set(gpo.index); oth={}
for ch in pd.read_csv(f"{G}/stop_times.txt",dtype=str,usecols=['trip_id','stop_id'],chunksize=2_000_000):
    ch=ch[ch.stop_id.isin(sset)&ch.trip_id.isin(tid.keys())]
    for sid,tr in zip(ch.stop_id,ch.trip_id): oth.setdefault(sid,set()).add(tid[tr])
gpo['other']=[' '.join(sorted(oth.get(i,()),key=lambda x:(len(x),x))) for i in gpo.index]
out(gpo[['stop_name','cls','ntrips','routes','rc','other','geometry']],'stops.geojson')
uq=gp[gp.hub=='UQ']
hubs=[]
for pid,d in uq.groupby(uq.stop_name.str.extract(r'^(.*?)(?:,|$)')[0]):
    agg={}
    for x in d.groups:
        for k,v in x.items(): agg[k]=agg.get(k,0)+v
    c=d.to_crs(4326).geometry.unary_union.centroid
    hubs.append(dict(name=pid,lat=round(c.y,5),lon=round(c.x,5),groups=agg,routes=sorted(set(sum(d.routes,[])),key=lambda x:(len(x),x))))
json.dump(dict(groups=gs,hubs=hubs,day=str(DAY),feed='Translink SEQ GTFS, 10 Oct – 9 Dec 2026'),open(f"{OUT}/meta.json","w"),indent=1)
print(json.dumps(hubs,indent=0)[:1500])
