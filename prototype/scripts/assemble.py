import sys,json,geopandas as gpd
S=sys.argv[1]; W=S+'/work'
z=gpd.read_file(W+'/zones.geojson').set_crs(4326,allow_override=True).to_crs(7856)
m=json.load(open(W+'/meta.json'))
for g in m['groups']:
    zz=z[z.cls==g['group']]
    if len(zz):
        parts=zz.explode(index_parts=False); big=parts.iloc[parts.area.values.argmax()]
        p=gpd.GeoSeries([big.geometry.representative_point()],crs=7856).to_crs(4326).iloc[0]
    else:
        p=gpd.GeoSeries([z.geometry.union_all().centroid],crs=7856).to_crs(4326).iloc[0]
    g['cx'],g['cy']=round(p.x,5),round(p.y,5)
    if g['group']=='40x': g['cx'],g['cy']=152.9925,-27.4848
t=open(S+'/scripts/page_template.html').read()
rep={'/*LEAFLETCSS*/':open(S+'/package/dist/leaflet.css').read(),'/*BASE*/':open(W+'/base.json').read(),'/*ZONES*/':open(W+'/zones.geojson').read(),
 '/*ROUTES*/':open(W+'/routes.geojson').read(),'/*STOPS*/':open(W+'/stops.geojson').read(),'/*CELLS*/':open(W+'/cells.geojson').read(),'/*RBUF*/':open(W+'/routebuf.geojson').read(),'/*GBUF*/':open(W+'/groupbuf.geojson').read(),'/*META*/':json.dumps(m,separators=(',',':'))}
for k,v in rep.items(): t=t.replace(k,v.replace('</','<\\/'))
open(S+'/site/route-territories.html','w').write(t)
print(round(len(t)/1e6,2),'MB')
