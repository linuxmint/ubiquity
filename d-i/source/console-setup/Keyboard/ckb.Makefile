base_parts = base.hdr.part  base.lists.part \
compat/base.lists.part \
HDR base.m_k.part   HDR base.l1_k.part        HDR base.l_k.part  \
HDR base.m_g.part \
HDR compat/base.mlv_s.part base.mlv_s.part \
HDR compat/base.ml_s.part  base.ml_s.part  \
HDR compat/base.ml1_s.part base.ml1_s.part \
HDR compat/base.ml1v1_s.part \
HDR compat/base.l2_s.part  base.l2_s.part  \
HDR compat/base.l3_s.part  base.l3_s.part  \
HDR compat/base.l4_s.part  base.l4_s.part  \
HDR compat/base.l2v2_s.part \
HDR compat/base.l3v3_s.part \
HDR compat/base.l4v4_s.part \
HDR base.m_s.part  HDR base.ml_c.part        HDR base.ml1_c.part \
HDR base.m_t.part \
HDR base.lo_s.part HDR base.l1o_s.part HDR base.l2o_s.part HDR base.l3o_s.part HDR base.l4o_s.part \
HDR compat/base.o_s.part base.o_s.part \
HDR base.o_c.part HDR base.o_t.part

base: $(base_parts)
	HDR="HDR" ./merge.sh $@ $+

transform_files=compat/layoutRename.lst compat/variantRename.lst

compat/base.l2_s.part: compat/ln_s.sh $(transform_files)
	cd compat && sh $(<F) 2

compat/base.l3_s.part: compat/ln_s.sh $(transform_files)
	cd compat && sh $(<F) 3

compat/base.l4_s.part: compat/ln_s.sh $(transform_files)
	cd compat && sh $(<F) 4

compat/base.l2v2_s.part: compat/lnv_s.sh $(transform_files)
	cd compat && sh $(<F) 2

compat/base.l3v3_s.part: compat/lnv_s.sh $(transform_files)
	cd compat && sh $(<F) 3

compat/base.l4v4_s.part: compat/lnv_s.sh $(transform_files)
	cd compat && sh $(<F) 4

compat/base.ml_s.part: compat/ml_s.sh $(transform_files)
	cd compat && sh $(<F)

compat/base.ml1_s.part: compat/ml1_s.sh $(transform_files)
	cd compat && sh $(<F)

compat/base.mlv_s.part: compat/mlv_s.sh $(transform_files)
	cd compat && sh $(<F)

compat/base.ml1v1_s.part: compat/ml1v1_s.sh $(transform_files)
	cd compat && sh $(<F)

.PHONY: clean
clean:
	-rm -f base.xml base compat/base.l2_s.part compat/base.l4_s.part compat/base.ml1v1_s.part compat/base.l2v2_s.part compat/base.l4v4_s.part compat/base.ml_s.part compat/base.l3_s.part compat/base.mlv_s.part compat/base.l3v3_s.part compat/base.ml1_s.part

base.xml: base.xml.in
	LC_ALL=C intltool-merge -x -u -c ../po/.intltool-merge-cache ../po base.xml.in base.xml
