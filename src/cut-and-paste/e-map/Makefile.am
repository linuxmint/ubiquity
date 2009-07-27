INCLUDES = \
	$(UBIQUITY_DEPENDS_CFLAGS) \
	-DMAP_DIR=\""$(pixmapsdir)"\"

LDADD = -lm $(UBIQUITY_DEPENDS_LIBS)
LIBS+=$(LDADD)

EXTRA_DIST= e-map-marshal.list

e-map-marshal.h: e-map-marshal.list
	( @GLIB_GENMARSHAL@ e-map-marshal.list --header > e-map-marshal.tmp \
	&& mv e-map-marshal.tmp e-map-marshal.h ) \
	|| ( rm -f e-map-marshal.tmp && exit 1 )

e-map-marshal.c: e-map-marshal.h
	( @GLIB_GENMARSHAL@ e-map-marshal.list --body > e-map-marshal.tmp \
	&& mv e-map-marshal.tmp e-map-marshal.c ) \
	|| ( rm -f e-map-marshal.tmp && exit 1 )

$(e_map_la_OBJECTS): e-map-marshal.h

noinst_LIBRARIES = libemap.a

libemap_a_CFLAGS = \
	-fPIC $(UBIQUITY_DEPENDS_CFLAGS)
	
BUILT_SOURCES= e-map-marshal.c	e-map-marshal.h

libemap_a_SOURCES = \
	e-map.c e-map.h \
	e-map-marshal.c e-map-marshal.h
