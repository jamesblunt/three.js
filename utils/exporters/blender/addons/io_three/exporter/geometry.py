import os
from .. import constants, logger
from . import base_classes, io, api


FORMAT_VERSION = 3


class Geometry(base_classes.BaseNode):
    def __init__(self, node, parent=None):
        logger.debug('Geometry().__init__(%s)', node)
        
        #@TODO: maybe better to have `three` constants for
        #       strings that are specific to `three` properties
        geo_type = constants.GEOMETRY.title()
        if parent.options.get(constants.GEOMETRY_TYPE):
            opt_type = parent.options[constants.GEOMETRY_TYPE]
            if opt_type == constants.BUFFER_GEOMETRY:
                geo_type = constants.BUFFER_GEOMETRY
            elif opt_type != constants.GEOMETRY:
                logger.error('Unknown geometry type %s', opt_type)

        logger.info('Setting %s to "%s"', node, geo_type)

        self._defaults[constants.TYPE] = geo_type
        base_classes.BaseNode.__init__(self, node, 
            parent=parent,
            type=geo_type)

    @property
    def animation_filename(self):
        compression = self.options.get(constants.COMPRESSION)
        if compression in (None, constants.NONE):
            ext = constants.JSON
        elif compression == constants.MSGPACK:
            ext = constants.PACK

        for key in (constants.MORPH_TARGETS, constants.ANIMATION):
            try:
                self[key]
                break
            except KeyError:
                pass
        else:
            logger.info('%s has no animation data', self.node)
            return

        return '%s.%s.%s' % (self.node, key, ext)

    @property
    def face_count(self):
        try:
            faces = self[constants.FACES]
        except KeyError:
            logger.debug('No parsed faces found')
            return 0

        length = len(faces)
        offset = 0
        bitset = lambda x,y: x & ( 1 << y )
        face_count = 0

        masks = (constants.MASK[constants.UVS],
            constants.MASK[constants.NORMALS],
            constants.MASK[constants.COLORS])

        while offset < length:
            bit = faces[offset]
            offset += 1
            face_count += 1

            is_quad = bitset(bit, constants.MASK[constants.QUAD])
            vector = 4 if is_quad else 3
            offset += vector

            if bitset(bit, constants.MASK[constants.MATERIALS]):
                offset += 1

            for mask in masks:
                if bitset(bit, mask):
                    offset += vector

        return face_count

    @property
    def metadata(self):
        metadata = {
            constants.GENERATOR: constants.THREE,
            constants.VERSION: FORMAT_VERSION
        }

        if self[constants.TYPE] == constants.GEOMETRY.title():
            self.__geometry_metadata(metadata)
        else:
            self.__buffer_geometry_metadata(metadata)

        return metadata

    def copy(self, scene=True):
        logger.debug('Geometry().copy(scene=%s)', scene)
        dispatch = {
            True: self._scene_format,
            False: self._geometry_format
        }
        data = dispatch[scene]()

        try:
            data[constants.MATERIALS] = self[constants.MATERIALS].copy()
        except KeyError:
            logger.debug('No materials to copy')

        return data

    def copy_textures(self):
        logger.debug('Geometry().copy_textures()')
        if self.options.get(constants.COPY_TEXTURES):
            texture_registration = self.register_textures()
            if texture_registration:
                logger.info('%s has registered textures', self.node)
                io.copy_registered_textures(
                    os.path.dirname(self.scene.filepath),
                    texture_registration)

    def parse(self):
        logger.debug('Geometry().parse()')
        if self[constants.TYPE] == constants.GEOMETRY.title():
            logger.info('Parsing Geometry format')
            self.__parse_geometry()
        else:
            logger.info('Parsing BufferGeometry format')
            self.__parse_buffer_geometry()

    def register_textures(self):
        logger.debug('Geometry().register_textures()')
        return api.mesh.texture_registration(self.node) 

    def write(self, filepath=None):
        logger.debug('Geometry().write(filepath=%s)', filepath)

        filepath = filepath or self.scene.filepath

        io.dump(filepath, self.copy(scene=False), 
            options=self.scene.options) 

        if self.options.get(constants.MAPS):
            logger.info('Copying textures for %s', self.node)
            self.copy_textures()

    def write_animation(self, filepath):
        logger.debug('Geometry().write_animation(%s)', filepath)

        for key in (constants.MORPH_TARGETS, constants.ANIMATION):
            try:
                data = self[key]
                break
            except KeyError:
                pass
        else:
            logger.info('%s has no animation data', self.node)
            return

        filepath = os.path.join(filepath, self.animation_filename)
        if filepath:
            logger.info('Dumping animation data to %s', filepath)
            io.dump(filepath, data, options=self.scene.options)
            return filepath
        else:
            logger.warning('Could not determine a filepath for '\
                'animation data. Nothing written to disk.')

    def _component_data(self):
        logger.debug('Geometry()._component_data()')
        
        if self[constants.TYPE] != constants.GEOMETRY.title():
            return self[constants.ATTRIBUTES]

        components = [constants.VERTICES, constants.FACES, 
            constants.UVS, constants.COLORS, constants.NORMALS,
            constants.BONES, constants.SKIN_WEIGHTS, 
            constants.SKIN_INDICES, constants.NAME,
            constants.INFLUENCES_PER_VERTEX]

        data = {}
        anim_components = [constants.MORPH_TARGETS, constants.ANIMATION]
        if self.options.get(constants.EMBED_ANIMATION):
            components.extend(anim_components)
        else:
            for component in anim_components:
                try:
                    self[component]
                except KeyError:
                    pass
                else:
                    data[component] = os.path.basename(
                        self.animation_filename) 
            else:
                logger.info('No animation data found for %s', self.node)

        for component in components:
            try:
                data[component] = self[component]
            except KeyError:
                logger.debug('Component %s not found', component)
                pass

        return data

    def _geometry_format(self):
        data = self._component_data()

        if self[constants.TYPE] != constants.GEOMETRY.title():
            data = {constants.ATTRIBUTES: data}

        data[constants.METADATA] = {
            constants.TYPE: self[constants.TYPE]
        }

        data[constants.METADATA].update(self.metadata)

        return data

    def __buffer_geometry_metadata(self, metadata):
        for key, value in self[constants.ATTRIBUTES].items():
            size = value[constants.ITEM_SIZE]
            array = value[constants.ARRAY]
            metadata[key] = len(array)/size
        
    def __geometry_metadata(self, metadata): 
        skip = (constants.TYPE, constants.FACES, constants.UUID,
            constants.ANIMATION, constants.SKIN_INDICES,
            constants.SKIN_WEIGHTS, constants.NAME, 
            constants.INFLUENCES_PER_VERTEX)
        vectors = (constants.VERTICES, constants.NORMALS)

        for key in self.keys():
            if key in vectors:
                try:
                    metadata[key] = int(len(self[key])/3)
                except KeyError:
                    pass
                continue

            if key in skip: continue

            metadata[key] = len(self[key])

        faces = self.face_count
        if faces > 0:
            metadata[constants.FACES] = faces

    def _scene_format(self):
        data = {
            constants.UUID: self[constants.UUID],
            constants.TYPE: self[constants.TYPE]
        }

        component_data = self._component_data()
        if self[constants.TYPE] == constants.GEOMETRY.title():
            data[constants.DATA] = component_data
            data[constants.DATA].update({
                constants.METADATA: self.metadata
            })
        else:
            if self.options[constants.EMBED_GEOMETRY]:
                data[constants.DATA] = {
                    constants.ATTRIBUTES: component_data
                }
            else:
                data[constants.ATTRIBUTES] = component_data
            data[constants.METADATA] = self.metadata 
            data[constants.NAME] = self[constants.NAME]

        return data 

    def __parse_buffer_geometry(self):
        self[constants.ATTRIBUTES] = {}

        options_vertices = self.options.get(constants.VERTICES)
        option_normals = self.options.get(constants.NORMALS)
        option_uvs = self.options.get(constants.UVS)

        dispatch = (
            (constants.POSITION, options_vertices, 
                api.mesh.buffer_position, 3), 
            (constants.UV, option_uvs, api.mesh.buffer_uv, 2), 
            (constants.NORMAL, option_normals, 
                api.mesh.buffer_normal, 3)
        )

        for key, option, func, size in dispatch: 

            if not option:
                continue

            array = func(self.node, self.options)
            if not array: 
                logger.warning('No array could be made for %s', key)
                continue

            self[constants.ATTRIBUTES][key] = {
                constants.ITEM_SIZE: size,
                constants.TYPE: constants.FLOAT_32,
                constants.ARRAY: array
            }

    def __parse_geometry(self):
        if self.options.get(constants.VERTICES):
            logger.info('Parsing %s', constants.VERTICES)
            self[constants.VERTICES] = api.mesh.vertices(
                self.node, self.options)

        if self.options.get(constants.FACES):
            logger.info('Parsing %s', constants.FACES)
            self[constants.FACES] = api.mesh.faces(
                self.node, self.options)

        if self.options.get(constants.NORMALS):
            logger.info('Parsing %s', constants.NORMALS)
            self[constants.NORMALS] = api.mesh.normals(
                self.node, self.options)

        if self.options.get(constants.COLORS):
            logger.info('Parsing %s', constants.COLORS)
            self[constants.COLORS] = api.mesh.vertex_colors(
                self.node)
        
        if self.options.get(constants.FACE_MATERIALS):
            logger.info('Parsing %s', constants.FACE_MATERIALS)
            self[constants.MATERIALS] = api.mesh.materials(
                self.node, self.options)

        if self.options.get(constants.UVS):
            logger.info('Parsing %s', constants.UVS)
            self[constants.UVS] = api.mesh.uvs(
                self.node, self.options)

        if self.options.get(constants.ANIMATION):
            logger.info('Parsing %s', constants.ANIMATION)
            self[constants.ANIMATION] = api.mesh.animation(
                self.node, self.options)

        #@TODO: considering making bones data implied when
        #       querying skinning data

        bone_map = {}
        if self.options.get(constants.BONES):
            logger.info('Parsing %s', constants.BONES)
            bones, bone_map = api.mesh.bones(self.node)
            self[constants.BONES] = bones

        if self.options.get(constants.SKINNING):
            logger.info('Parsing %s', constants.SKINNING)
            influences = self.options.get(
                constants.INFLUENCES_PER_VERTEX, 2)

            self[constants.INFLUENCES_PER_VERTEX] = influences
            self[constants.SKIN_INDICES] = api.mesh.skin_indices(
                self.node, bone_map, influences)
            self[constants.SKIN_WEIGHTS] = api.mesh.skin_weights(
                self.node, bone_map, influences)

        if self.options.get(constants.MORPH_TARGETS):
            logger.info('Parsing %s', constants.MORPH_TARGETS)
            self[constants.MORPH_TARGETS] = api.mesh.morph_targets(
                self.node, self.options)

