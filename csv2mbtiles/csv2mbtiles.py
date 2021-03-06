#!/usr/bin/env python

#Import system
import sys, os
from optparse import OptionParser
import shutil
import subprocess

#Import GDAL libraries
from osgeo import gdal
from osgeo import ogr
from osgeo import osr
from osgeo import gdal_array
from osgeo import gdalconst

#Import GDAL2Tiles
import gdal2tiles
from gdal2tiles import Configuration

#Import OGR2OGR
import ogr2ogr

def main(argv):
   #Get input and output from command line args
   parser = OptionParser()
   parser.add_option("-i", "--input", dest="inputfile",
                     help="Input csv file path", metavar="FILE")
   parser.add_option("-o", "--output", dest="outfile", default="./tmp/mbtiles.mbtiles",
                     help="Output MBtiles file path. Default is ./tmp/mbtiles.mbtiles", metavar="FILE")
   parser.add_option("-a", "--alg", dest="alg", default="invdist:power=2.0:smoothing=1.0",
                     help="GDAL grid algorithm. Default is 'invdist:power=2.0:smoothing=1.0'")
   parser.add_option("-m", "--zoom", dest="zoom", default="1-3",
                     help="Zoom level in single quotes. Default is '1-3'")
   parser.add_option("-c", "--color1", dest="color1", default='255 255 0',
                     help="RGB color for lowest level, Default '255 255 0' for yellow")
   parser.add_option("-d", "--color2", dest="color2", default='255 0 0',
                     help="RGB color for highest level, Default is '255 0 0' for red")
   parser.add_option("-n", "--nearest", dest="nearest", default=False,
                     help="If true, raster values will be assigned to nearest step, rather than continuous. Default is continuous. To be used in conjunction with -s")
   parser.add_option("-s", "--steps", dest="steps", default=10,
                     help="Number of steps in the color relief if specified and -n is 'True'. Default is 10")
   parser.add_option("-r", "--rows", dest="rows", default=1000,
                     help="Grid rows. Default is 1000")
   parser.add_option("-l", "--cols", dest="cols", default=1000,
                     help="Grid columns. Default is 1000")
   parser.add_option("-x", "--longitude", dest="longitude", default='longitude',
                     help="CSV longitude header. Default is 'longitude'")
   parser.add_option("-y", "--latitude", dest="latitude", default='latitude',
                     help="CSV latitude header. Default is 'latitude'")
   parser.add_option("-z", "--zfield", dest="zfield",
                     help="CSV z-field header")
   parser.add_option("-p", "--clipshape", dest="clipshape", default="./tmp/convexhull.shp",
                     help="Shapefile to clip tif. Default is generated convex-hull")
   (options, args) = parser.parse_args()
   basename = os.path.basename(options.inputfile)
   inputname, inputextension = os.path.splitext(basename)
   #Clean up
   try:
      shutil.rmtree("./tmp")
   except:
      print "No cleanup required... Continuing..."
   #Write DBF
   os.makedirs("./tmp")
   ogr2ogr.main(["","-f","ESRI Shapefile","./tmp",options.inputfile])
   #Write VRT
   print "Writing CSV VRT..."
   vrt = open('./tmp/'+inputname+'.vrt','w')
   vrt.write("<OGRVRTDataSource>\n")
   vrt.write("\t<OGRVRTLayer name='"+inputname+"'>\n")
   vrt.write("\t\t<SrcDataSource relativeToVRT='1'>./</SrcDataSource>\n")
   vrt.write("\t\t<GeometryType>wkbPoint</GeometryType>\n")
   vrt.write("\t\t<LayerSRS>WGS84</LayerSRS>\n")
   vrt.write("\t\t<GeometryField encoding='PointFromColumns' x='"+options.longitude+"' y='"+options.latitude+"'/>\n")
   vrt.write("\t</OGRVRTLayer>\n")
   vrt.write("</OGRVRTDataSource>")
   vrt.close()
   #Write SHP
   print "Converting to SHP..."
   ogr2ogr.main(["","-f","ESRI Shapefile","./tmp","./tmp/"+inputname+".vrt","-overwrite"])
   
   #Rasterize SHP
   print "Rasterizing..."
   rasterize = subprocess.Popen(["gdal_grid","-outsize",str(options.rows),str(options.cols),"-a",options.alg,"-zfield",options.zfield,"./tmp/"+inputname+".shp","-l",inputname,"./tmp/"+inputname+".tif","--config", "GDAL_NUM_THREADS", "ALL_CPUS"], stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   rOutput = rasterize.communicate()[0]
   print rOutput
   
   #Convex hull
   # Get a Layer
   print "Calculating convex hull..."
   inShapefile = "./tmp/"+inputname+".shp"
   inDriver = ogr.GetDriverByName("ESRI Shapefile")
   inDataSource = inDriver.Open(inShapefile, 0)
   inLayer = inDataSource.GetLayer()
   
   # Collect all Geometry
   geomcol = ogr.Geometry(ogr.wkbGeometryCollection)
   for feature in inLayer:
       geomcol.AddGeometry(feature.GetGeometryRef())
   
   # Calculate convex hull
   convexhull = geomcol.ConvexHull()
   
   # Save extent to a new Shapefile
   outShapefile = "./tmp/convexhull.shp"
   outDriver = ogr.GetDriverByName("ESRI Shapefile")
   
   # Remove output shapefile if it already exists
   if os.path.exists(outShapefile):
       outDriver.DeleteDataSource(outShapefile)
   
   # Create the output shapefile
   outDataSource = outDriver.CreateDataSource(outShapefile)
   outLayer = outDataSource.CreateLayer("convexhull", geom_type=ogr.wkbPolygon)
   
   # Add an ID field
   idField = ogr.FieldDefn("id", ogr.OFTInteger)
   outLayer.CreateField(idField)
   
   # Create the feature and set values
   featureDefn = outLayer.GetLayerDefn()
   feature = ogr.Feature(featureDefn)
   feature.SetGeometry(convexhull)
   feature.SetField("id", 1)
   outLayer.CreateFeature(feature)
   
   # Close DataSource
   inDataSource.Destroy()
   outDataSource.Destroy()
   
   #Write color relief txt
   print "Writing color relief txt..."
   steps = int(options.steps)
   colorTxt = open("./tmp/"+"color.txt","w")
   colorTxt.write("0% "+options.color1+"\n")
   percentStep = 100/float(steps)
   for step in range(1,steps):
      percentR = str(((int(options.color1.split()[0])*(steps-step))+(int(options.color2.split()[0])*step))/steps)
      percentG = str(((int(options.color1.split()[1])*(steps-step))+(int(options.color2.split()[1])*step))/steps)
      percentB = str(((int(options.color1.split()[2])*(steps-step))+(int(options.color2.split()[2])*step))/steps)
      colorTxt.write(str(percentStep*step)+"% "+percentR+" "+percentG+" "+percentB+" "+"\n")
   colorTxt.write("100% "+options.color2)
   colorTxt.close()
   
   #Color the raster
   print "Colorizing raster..."
   if options.nearest:
      colorize = subprocess.Popen(["gdaldem", "color-relief","./tmp/"+inputname+".tif", "./tmp/color.txt", "./tmp/"+inputname+"_color.tif","-nearest_color_entry"], stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   else:
      colorize = subprocess.Popen(["gdaldem", "color-relief","./tmp/"+inputname+".tif", "./tmp/color.txt", "./tmp/"+inputname+"_color.tif"], stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   cOutput = colorize.communicate()[0]
   print cOutput
   
   #Warp for compression and clip to convex hull
   print "Warping raster..."
   warp = subprocess.Popen(["gdalwarp","-co","compress=deflate", "-co", "tiled=yes", "-r", "lanczos", "-cutline", options.clipshape, "-dstnodata", "0", "./tmp/"+inputname+"_color.tif", "./tmp/"+inputname+"_final.tif"], stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   wOutput = warp.communicate()[0]
   print wOutput
   
   #Draw VRT for parallel gdal2tiles
   print "Building tile VRT..."
   buildVrt = subprocess.Popen(["gdalbuildvrt","./tmp/tiles.vrt", "./tmp/"+inputname+"_final.tif"], stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   vOutput = buildVrt.communicate()[0]
   print vOutput
   
   #Draw png tiles
   print "Drawing tiles..."
   argv = gdal.GeneralCmdLineProcessor( ['./gdal2tiles.py','-z',options.zoom,'./tmp/tiles.vrt','./tmp/tiles'] )
   if argv:
      c1 = Configuration(argv[1:])
      tile=c1.create_tile()
      gdal2tiles.process(c1,tile)
       
   #Create MBtiles
   print "Generating MBtiles file..."
   mbtiles = subprocess.Popen(["mb-util","./tmp/tiles",options.outfile,"--scheme","tms"], stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   mOutput = mbtiles.communicate()[0]
   print mOutput
   print "Done."

if __name__ == "__main__":
   main(sys.argv[1:])
