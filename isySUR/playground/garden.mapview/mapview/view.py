# coding=utf-8

__all__ = ["MapView", "MapMarker", "MapMarkerPopup", "MapLayer", "MarkerMapLayer"]

from os.path import join, dirname
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivy.uix.image import Image
from kivy.uix.scatter import Scatter
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import NumericProperty, ObjectProperty, ListProperty, \
    AliasProperty, BooleanProperty
from kivy.graphics import Canvas, Color, Rectangle, Mesh
from kivy.graphics.transformation import Matrix
from kivy.lang import Builder
from kivy.compat import string_types
from math import ceil
from mapview import MIN_LONGITUDE, MAX_LONGITUDE, MIN_LATITUDE, MAX_LATITUDE, \
    CACHE_DIR, Coordinate, Bbox
from mapview.source import MapSource
from mapview.utils import clamp


Builder.load_string("""
<MapMarker>:
    size_hint: None, None
    source: root.default_marker_fn
    size: list(map(dp, self.texture_size))
    allow_stretch: True

<MapView>:
    canvas.before:
        StencilPush
        Rectangle:
            pos: self.pos
            size: self.size
        StencilUse
        Color:
            rgba: self.background_color
        Rectangle:
            pos: self.pos
            size: self.size
    canvas.after:
        StencilUnUse
        Rectangle:
            pos: self.pos
            size: self.size
        StencilPop

    Label:
        text: root.map_source.attribution if hasattr(root.map_source, "attribution") else ""
        size_hint: None, None
        size: self.texture_size[0] + sp(8), self.texture_size[1] + sp(4)
        font_size: "10sp"
        right: [root.right, self.center][0]
        color: 0, 0, 0, 1
        canvas.before:
            Color:
                rgba: .8, .8, .8, .8
            Rectangle:
                pos: self.pos
                size: self.size


<MapViewScatter>:
    auto_bring_to_front: False
    do_rotation: False
    scale_min: 0.2
    scale_max: 3.

<MapMarkerPopup>:
    RelativeLayout:
        id: placeholder
        y: root.top
        center_x: root.center_x
        size: root.popup_size

""")


class Tile(Rectangle):
    @property
    def cache_fn(self):
        map_source = self.map_source
        fn = map_source.cache_fmt.format(
            image_ext=map_source.image_ext,
            cache_key=map_source.cache_key,
            **self.__dict__)
        return join(CACHE_DIR, fn)

    def set_source(self, cache_fn):
        self.source = cache_fn
        self.state = "need-animation"


class MapMarker(ButtonBehavior, Image):
    """A marker on a map, that must be used on a :class:`MapMarker`
    """

    anchor_x = NumericProperty(0.5)
    """Anchor of the marker on the X axis. Defaults to 0.5, mean the anchor will
    be at the X center of the image.
    """

    anchor_y = NumericProperty(0)
    """Anchor of the marker on the Y axis. Defaults to 0, mean the anchor will
    be at the Y bottom of the image.
    """

    lat = NumericProperty(0)
    """Latitude of the marker
    """

    lon = NumericProperty(0)
    """Longitude of the marker
    """

    @property
    def default_marker_fn(self):
        return join(dirname(__file__), "icons", "marker.png")


class MapMarkerPopup(MapMarker):
    is_open = BooleanProperty(False)
    placeholder = ObjectProperty(None)
    popup_size = ListProperty([100, 100])

    def add_widget(self, widget):
        if not self.placeholder:
            self.placeholder = widget
            if self.is_open:
                super(MapMarkerPopup, self).add_widget(self.placeholder)
        else:
            self.placeholder.add_widget(widget)

    def remove_widget(self, widget):
        if widget is not self.placeholder:
            self.placeholder.remove_widget(widget)
        else:
            super(MarkerMapLayer, self).remove_widget(widget)

    def on_is_open(self, *args):
        self.refresh_open_status()

    def on_release(self, *args):
        self.is_open = not self.is_open

    def refresh_open_status(self):
        if not self.is_open and self.placeholder.parent:
            super(MapMarkerPopup, self).remove_widget(self.placeholder)
        elif self.is_open and not self.placeholder.parent:
            super(MapMarkerPopup, self).add_widget(self.placeholder)


class MapLayer(Widget):
    """A map layer, that is repositionned everytime the :class:`MapView` is
    moved.
    """
    viewport_x = NumericProperty(0)
    viewport_y = NumericProperty(0)

    def reposition(self):
        """Function called when :class:`MapView` is moved. You must recalculate
        the position of your children.
        """
        pass

    def unload(self):
        """Called when the view want to completly unload the layer.
        """
        pass
      
class PolyMapLayer(MapLayer):
    """A map layer for :class:`MapMarker`
    """

    def __init__(self, **kwargs):
        super(PolyMapLayer, self).__init__(**kwargs)

    def add_widget(self, marker):
        super(PolyMapLayer, self).add_widget(marker)

    def remove_widget(self, marker):
        super(PolyMapLayer, self).remove_widget(marker)


    def unload(self):
        self.clear_widgets()

class MarkerMapLayer(MapLayer):
    """A map layer for :class:`MapMarker`
    """

    def __init__(self, **kwargs):
        self.markers = []
        super(MarkerMapLayer, self).__init__(**kwargs)

    def add_widget(self, marker):
        self.markers.append(marker)
        super(MarkerMapLayer, self).add_widget(marker)

    def remove_widget(self, marker):
        if marker in self.markers:
            self.markers.remove(marker)
        super(MarkerMapLayer, self).remove_widget(marker)

    def reposition(self):
        mapview = self.parent
        set_marker_position = self.set_marker_position
        bbox = mapview.get_bbox(dp(48))
        for marker in self.markers:
            if bbox.collide(marker.lat, marker.lon):
                set_marker_position(mapview, marker)
                if marker.parent:
                    continue
                super(MarkerMapLayer, self).add_widget(marker)
            else:
                if not marker.parent:
                    continue
                super(MarkerMapLayer, self).remove_widget(marker)

    def set_marker_position(self, mapview, marker):
        x, y = mapview.get_window_xy_from(marker.lat, marker.lon, mapview.zoom)
        marker.x = int(x - marker.width * marker.anchor_x)
        marker.y = int(y - marker.height * marker.anchor_y)

    def unload(self):
        self.clear_widgets()
        del self.markers[:]


class MapViewScatter(Scatter):
    # internal
    def on_transform(self, *args):
        super(MapViewScatter, self).on_transform(*args)
        self.parent.on_transform(self.transform)

    def collide_point(self, x, y):
        #print "collide_point", x, y
        return True


class MapView(Widget):
    """MapView is the widget that control the map displaying, navigation, and
    layers management.
    """

    lon = NumericProperty()
    """Longitude at the center of the widget
    """

    lat = NumericProperty()
    """Latitude at the center of the widget
    """

    zoom = NumericProperty(0)
    """Zoom of the widget. Must be between :meth:`MapSource.get_min_zoom` and
    :meth:`MapSource.get_max_zoom`. Default to 0.
    """

    map_source = ObjectProperty(MapSource())
    """Provider of the map, default to a empty :class:`MapSource`.
    """

    double_tap_zoom = BooleanProperty(False)
    """If True, this will activate the double-tap to zoom.
    """

    delta_x = NumericProperty(0)
    delta_y = NumericProperty(0)
    background_color = ListProperty([181 / 255., 208 / 255., 208 / 255., 1])
    _zoom = NumericProperty(0)

    __events__ = ["on_map_relocated"]

    # Public API

    @property
    def viewport_pos(self):
        vx, vy = self._scatter.to_local(self.x, self.y)
        return vx - self.delta_x, vy - self.delta_y

    @property
    def scale(self):
        return self._scatter.scale

    def get_bbox(self, margin=0):
        """Returns the bounding box from the bottom/left (lat1, lon1) to
        top/right (lat2, lon2).
        """
        x1, y1 = self.to_local(0 - margin, 0 - margin)
        x2, y2 = self.to_local((self.width + margin) / self.scale,
                               (self.height + margin) / self.scale)
        c1 = self.get_latlon_at(x1, y1)
        c2 = self.get_latlon_at(x2, y2)
        return Bbox((c1.lat, c1.lon, c2.lat, c2.lon))

    bbox = AliasProperty(get_bbox, None, bind=["lat", "lon", "_zoom"])

    def unload(self):
        """Unload the view and all the layers.
        It also cancel all the remaining downloads.
        """
        self.remove_all_tiles()

    def get_window_xy_from(self, lat, lon, zoom):
        """Returns the x/y position in the widget absolute coordinates
        from a lat/lon"""
        vx, vy = self.viewport_pos
        x = self.map_source.get_x(zoom, lon) - vx
        y = self.map_source.get_y(zoom, lat) - vy
        x *= self.scale
        y *= self.scale
        return x, y

    def center_on(self, *args):
        """Center the map on the coordinate :class:`Coordinate`, or a (lat, lon)
        """
        map_source = self.map_source
        zoom = self._zoom

        if len(args) == 1 and isinstance(args[0], Coordinate):
            lat = coord.lat
            lon = coord.lon
        elif len(args) == 2:
            lat, lon = args
        else:
            raise Exception("Invalid argument for center_on")
        lon = clamp(lon, MIN_LONGITUDE, MAX_LONGITUDE)
        lat = clamp(lat, MIN_LATITUDE, MAX_LATITUDE)
        scale = self._scatter.scale
        x = map_source.get_x(zoom, lon) - self.center_x / scale
        y = map_source.get_y(zoom, lat) - self.center_y / scale
        self.delta_x = -x
        self.delta_y = -y
        self._scatter.pos = 0, 0
        self.trigger_update(True)

    def set_zoom_at(self, zoom, x, y, scale=None):
        """Sets the zoom level, leaving the (x, y) at the exact same point
        in the view.
        """
        zoom = clamp(zoom,
                     self.map_source.get_min_zoom(),
                     self.map_source.get_max_zoom())
        if int(zoom) == int(self._zoom):
            return
        scale = scale or 1.

        # first, rescale the scatter
        scatter = self._scatter
        scale = clamp(scale, scatter.scale_min, scatter.scale_max)
        rescale = scale * 1.0 / scatter.scale
        scatter.apply_transform(Matrix().scale(rescale, rescale, rescale),
                             post_multiply=True,
                             anchor=scatter.to_local(x, y))

        # adjust position if the zoom changed
        c1 = self.map_source.get_col_count(self._zoom)
        c2 = self.map_source.get_col_count(zoom)
        if c1 != c2:
            f = float(c2) / float(c1)
            self.delta_x = scatter.x + self.delta_x * f
            self.delta_y = scatter.y + self.delta_y * f
            # back to 0 every time
            scatter.apply_transform(Matrix().translate(
                -scatter.x, -scatter.y, 0
            ), post_multiply=True)

        # avoid triggering zoom changes.
        self._zoom = zoom
        self.zoom = self._zoom

    def on_zoom(self, instance, zoom):
        if zoom == self._zoom:
            return
        x = self.map_source.get_x(zoom, self.lon) - self.delta_x
        y = self.map_source.get_y(zoom, self.lat) - self.delta_y
        self.set_zoom_at(zoom, x, y)
        self.center_on(self.lat, self.lon)
        self.drawPolygon()

    def get_latlon_at(self, x, y, zoom=None):
        """Return the current :class:`Coordinate` within the (x, y) widget
        coordinate.
        """
        if zoom is None:
            zoom = self._zoom
        vx, vy = self.viewport_pos
        return Coordinate(
            lat=self.map_source.get_lat(zoom, y + vy),
            lon=self.map_source.get_lon(zoom, x + vx))

    def add_marker(self, marker, layer=None):
        """Add a marker into the layer. If layer is None, it will be added in
        the default marker layer. If there is no default marker layer, a new
        one will be automatically created
        """
        if layer is None:
            if not self._default_marker_layer:
                layer = MarkerMapLayer()
                self.add_layer(layer)
            else:
                layer = self._default_marker_layer
        layer.add_widget(marker)
        layer.set_marker_position(self, marker)
        
        
    def drawPolygon(self):
      
      self.polyLayer.canvas.clear()
      self.kmls = [[(5.34109800,50.93274000),(5.34114700,50.93278900),(5.34116100,50.93278200),
                  (5.34169600,50.93300200),(5.34174800,50.93295100),(5.34183200,50.93298500),
                  (5.34209100,50.93273400),(5.34206900,50.93272500),(5.34212200,50.93268000),
                  (5.34213600,50.93268600),(5.34223900,50.93258700),(5.34184300,50.93242600),
                  (5.34109800,50.93274000)]]                
      for kml in self.kmls:
        vertices = []
        indices = []
        i = 0
        for coords in kml:
  #        x,y = self.get_xy_from_latlon(coords[1],coords[0])
          x,y = self.get_window_xy_from(coords[1],coords[0], self._zoom)
        
          vertices.extend([x,y,0,0])
          indices.append(i)
          i+=1
  #        points.append(y)
        with self.polyLayer.canvas:
          Color(1,0,0,0.8, mode='rgba')
  #        Line(points=points)
          Mesh(vertices=vertices, indices=indices, mode="triangle_fan")

    def remove_marker(self, marker):
        """Remove a marker from its layer
        """
        marker.detach()

    def add_layer(self, layer, mode="window"):
        """Add a new layer to update at the same time the base tile layer.
        mode can be either "scatter" or "window". If "scatter", it means the
        layer will be within the scatter transformation. It's perfect if you
        want to display path / shape, but not for text.
        If "window", it will have no transformation. You need to position the
        widget yourself: think as Z-sprite / billboard.
        Defaults to "window".
        """
        assert(mode in ("scatter", "window"))
        if self._default_marker_layer is None and \
            isinstance(layer, MarkerMapLayer):
            self._default_marker_layer = layer
        self._layers.append(layer)
        c = self.canvas
        if mode == "scatter":
            self.canvas = self.canvas_layers
        else:
            self.canvas = self.canvas_layers_out
        layer.canvas_parent = self.canvas
        super(MapView, self).add_widget(layer)
        self.canvas = c

    def remove_layer(self, layer):
        """Remove the layer
        """
        self._layers.remove(layer)
        self.canvas = layer.canvas_parent
        super(MapView, self).remove_widget(layer)
        self.canvas = c

    def sync_to(self, other):
        """Reflect the lat/lon/zoom of the other MapView to the current one.
        """
        if self._zoom != other._zoom:
            self.set_zoom_at(other._zoom, *self.center)
        self.center_on(other.get_latlon_at(*self.center))


    # Private API

    def __init__(self, **kwargs):
        from kivy.base import EventLoop
        EventLoop.ensure_window()
        self._tiles = []
        self._tiles_bg = []
        self._tilemap = {}
        self._layers = []
        self._default_marker_layer = None
        self._need_redraw_all = False
        self._transform_lock = False
        self.trigger_update(True)
        self.canvas = Canvas()
        self._scatter = MapViewScatter()
        self.add_widget(self._scatter)
        with self._scatter.canvas:
            self.canvas_map = Canvas()
            self.canvas_layers = Canvas()
        with self.canvas:
            self.canvas_layers_out = Canvas()
        self._scale_target_anim = False
        self._scale_target = 1.
        Clock.schedule_interval(self._animate_color, 1 / 60.)
        
        self.polyLayer = PolyMapLayer()
        self.add_layer(self.polyLayer)  

        super(MapView, self).__init__(**kwargs)

    def _animate_color(self, dt):
        for tile in self._tiles:
            if tile.state != "need-animation":
                continue
            tile.g_color.a += dt * 10.  # 100ms
            if tile.g_color.a >= 1:
                tile.state = "animated"
        for tile in self._tiles_bg:
            if tile.state != "need-animation":
                continue
            tile.g_color.a += dt * 10.  # 100ms
            if tile.g_color.a >= 1:
                tile.state = "animated"

    def add_widget(self, widget):
        if isinstance(widget, MapMarker):
            self.add_marker(widget)
        elif isinstance(widget, MapLayer):
            self.add_layer(widget)
        else:
            super(MapView, self).add_widget(widget)

    def remove_widget(self, widget):
        if isinstance(widget, MapMarker):
            self.remove_marker(widget)
        elif isinstance(widget, MapLayer):
            self.remove_layer(widget)
        else:
            super(MapView, self).remove_widget(widget)

    def on_map_relocated(self, zoom, coord):
        pass

    def animated_diff_scale_at(self, d, x, y):
        self._scale_target_time = 1.
        self._scale_target_pos = x, y
        if self._scale_target_anim == False:
            self._scale_target_anim = True
            self._scale_target = d
        else:
            self._scale_target += d
        Clock.unschedule(self._animate_scale)
        Clock.schedule_interval(self._animate_scale, 1 / 60.)

    def _animate_scale(self, dt):
        diff = self._scale_target / 3.
        if abs(diff) < 0.01:
            diff = self._scale_target
            self._scale_target = 0
        else:
            self._scale_target -= diff
        self._scale_target_time -= dt
        self.diff_scale_at(diff, *self._scale_target_pos)
        return self._scale_target != 0

    def diff_scale_at(self, d, x, y):
        scatter = self._scatter
        scale = scatter.scale * (2 ** d)
        self.scale_at(scale, x, y)

    def scale_at(self, scale, x, y):
        scatter = self._scatter
        scale = clamp(scale, scatter.scale_min, scatter.scale_max)
        rescale = scale * 1.0 / scatter.scale
        scatter.apply_transform(Matrix().scale(rescale, rescale, rescale),
                             post_multiply=True,
                             anchor=scatter.to_local(x, y))

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return
        if "button" in touch.profile and touch.button in ("scrolldown", "scrollup"):
            d = 1 if touch.button == "scrollup" else -1
            self.animated_diff_scale_at(d * 0.25, *touch.pos)
            return True
        elif touch.is_double_tap and self.double_tap_zoom:
            self.animated_diff_scale_at(1, *touch.pos)
            return True
        return super(MapView, self).on_touch_down(touch)

    def on_transform(self, *args):
       
        if self._transform_lock:
            return
        self._transform_lock = True
        # recalculate viewport
        zoom = self._zoom
        scatter = self._scatter
        scale = scatter.scale
        if scale >= 2.:
            zoom += 1
            scale /= 2.
        elif scale < 1:
            zoom -= 1
            scale *= 2.
        zoom = clamp(zoom, self.map_source.min_zoom, self.map_source.max_zoom)
        if zoom != self._zoom:
            self.set_zoom_at(zoom, scatter.x, scatter.y, scale=scale)
            self.trigger_update(True)
        else:
            self.trigger_update(False)
        self._transform_lock = False
        self.drawPolygon()

    def trigger_update(self, full):
        self._need_redraw_full = full or self._need_redraw_full
        Clock.unschedule(self.do_update)
        Clock.schedule_once(self.do_update, -1)

    def do_update(self, dt):
        zoom = self._zoom
        self.lon = self.map_source.get_lon(zoom, self.center_x - self._scatter.x - self.delta_x)
        self.lat = self.map_source.get_lat(zoom, self.center_y - self._scatter.y - self.delta_y)
        for layer in self._layers:
            layer.reposition()
        self.dispatch("on_map_relocated", zoom, Coordinate(self.lon, self.lat))

        if self._need_redraw_full:
            self._need_redraw_full = False
            self.move_tiles_to_background()
            self.load_visible_tiles()
        else:
            self.load_visible_tiles()

    def bbox_for_zoom(self, vx, vy, w, h, zoom):
        # return a tile-bbox for the zoom
        map_source = self.map_source
        size = map_source.dp_tile_size
        scale = self.scale

        max_x_end = map_source.get_col_count(zoom)
        max_y_end = map_source.get_row_count(zoom)

        x_count = int(ceil(w / scale / float(size))) + 1
        y_count = int(ceil(h / scale / float(size))) + 1

        tile_x_first = int(clamp(vx / float(size), 0, max_x_end))
        tile_y_first = int(clamp(vy / float(size), 0, max_y_end))
        tile_x_last = tile_x_first + x_count
        tile_y_last = tile_y_first + y_count
        tile_x_last = int(clamp(tile_x_last, tile_x_first, max_x_end))
        tile_y_last = int(clamp(tile_y_last, tile_y_first, max_y_end))

        x_count = tile_x_last - tile_x_first
        y_count = tile_y_last - tile_y_first
        return (tile_x_first, tile_y_first, tile_x_last, tile_y_last,
                x_count, y_count)

    def load_visible_tiles(self):
        map_source = self.map_source
        vx, vy = self.viewport_pos
        zoom = self._zoom
        dirs = [0, 1, 0, -1, 0]
        bbox_for_zoom = self.bbox_for_zoom
        size = map_source.dp_tile_size

        tile_x_first, tile_y_first, tile_x_last, tile_y_last, \
            x_count, y_count = bbox_for_zoom(vx, vy, self.width, self.height, zoom)

        #print "Range {},{} to {},{}".format(
        #    tile_x_first, tile_y_first,
        #    tile_x_last, tile_y_last)

        # Adjust tiles behind us
        for tile in self._tiles_bg[:]:
            tile_x = tile.tile_x
            tile_y = tile.tile_y

            f = 2 ** (zoom - tile.zoom)
            w = self.width / f
            h = self.height / f
            btile_x_first, btile_y_first, btile_x_last, btile_y_last, \
                _, _ = bbox_for_zoom(vx / f, vy / f, w, h, tile.zoom)

            if tile_x < btile_x_first or tile_x >= btile_x_last or \
               tile_y < btile_y_first or tile_y >= btile_y_last:
               tile.state = "done"
               self._tiles_bg.remove(tile)
               self.canvas_map.before.remove(tile.g_color)
               self.canvas_map.before.remove(tile)
               continue

            tsize = size * f
            tile.size = tsize, tsize
            tile.pos = (
                tile_x * tsize + self.delta_x,
                tile_y * tsize + self.delta_y)

        # Get rid of old tiles first
        for tile in self._tiles[:]:
            tile_x = tile.tile_x
            tile_y = tile.tile_y

            if tile_x < tile_x_first or tile_x >= tile_x_last or \
               tile_y < tile_y_first or tile_y >= tile_y_last:
                tile.state = "done"
                self.tile_map_set(tile_x, tile_y, False)
                self._tiles.remove(tile)
                self.canvas_map.remove(tile)
                self.canvas_map.remove(tile.g_color)
            else:
                tile.size = (size, size)
                tile.pos = (tile_x * size + self.delta_x, tile_y * size + self.delta_y)

        # Load new tiles if needed
        x = tile_x_first + x_count // 2 - 1
        y = tile_y_first + y_count // 2 - 1
        arm_max = max(x_count, y_count) + 2
        arm_size = 1
        turn = 0
        while arm_size < arm_max:
            for i in range(arm_size):
                if not self.tile_in_tile_map(x, y) and \
                   y >= tile_y_first and y < tile_y_last and \
                   x >= tile_x_first and x < tile_x_last:
                    self.load_tile(x, y, size, zoom)

                x += dirs[turn % 4 + 1]
                y += dirs[turn % 4]

            if turn % 2 == 1:
                arm_size += 1

            turn += 1

    def load_tile(self, x, y, size, zoom):
        map_source = self.map_source
        if self.tile_in_tile_map(x, y) or zoom != self._zoom:
            return
        self.load_tile_for_source(self.map_source, 1., size, x, y, zoom)
        # XXX do overlay support
        self.tile_map_set(x, y, True)

    def load_tile_for_source(self, map_source, opacity, size, x, y, zoom):
        tile = Tile(size=(size, size))
        tile.g_color = Color(1, 1, 1, 0)
        tile.tile_x = x
        tile.tile_y = y
        tile.zoom = zoom
        tile.pos = (x * size + self.delta_x, y * size + self.delta_y)
        tile.map_source = map_source
        tile.state = "loading"
        map_source.fill_tile(tile)
        self.canvas_map.add(tile.g_color)
        self.canvas_map.add(tile)
        self._tiles.append(tile)

    def move_tiles_to_background(self):
        # remove all the tiles of the main map to the background map
        # retain only the one who are on the current zoom level
        # for all the tile in the background, stop the download if not yet started.
        zoom = self._zoom
        tiles = self._tiles
        btiles = self._tiles_bg
        canvas_map = self.canvas_map
        tile_size = self.map_source.tile_size

        # move all tiles to background
        while tiles:
            tile = tiles.pop()
            if tile.state == "loading":
                tile.state == "done"
                continue
            btiles.append(tile)

        # clear the canvas
        self.canvas_map.clear()
        self.canvas_map.before.clear()
        self._tilemap = {}

        # unsure if it's really needed, i personnally didn't get issues right now
        #btiles.sort(key=lambda z: -z.zoom)

        # add all the btiles into the back canvas.
        # except for the tiles that are owned by the current zoom level
        for tile in btiles[:]:
            if tile.zoom == zoom:
                btiles.remove(tile)
                tiles.append(tile)
                tile.size = tile_size, tile_size
                canvas_map.add(tile.g_color)
                canvas_map.add(tile)
                self.tile_map_set(tile.tile_x, tile.tile_y, True)
                continue
            canvas_map.before.add(tile.g_color)
            canvas_map.before.add(tile)

    def remove_all_tiles(self):
        # clear the map of all tiles.
        self.canvas_map.clear()
        self.canvas_map.before.clear()
        for tile in self._tiles:
            tile.state = "done"
        del self._tiles[:]
        del self._tiles_bg[:]
        self._tilemap = {}

    def tile_map_set(self, tile_x, tile_y, value):
        key = tile_y * self.map_source.get_col_count(self._zoom) + tile_x
        if value:
            self._tilemap[key] = value
        else:
            self._tilemap.pop(key, None)

    def tile_in_tile_map(self, tile_x, tile_y):
        key = tile_y * self.map_source.get_col_count(self._zoom) + tile_x
        return key in self._tilemap

    def on_size(self, instance, size):
        for layer in self._layers:
            layer.size = size
        self.center_on(self.lat, self.lon)
        self.trigger_update(True)

    def on_pos(self, instance, pos):
        self.center_on(self.lat, self.lon)
        self.trigger_update(True)

    def on_map_source(self, instance, source):
        if isinstance(source, string_types):
            self.map_source = MapSource.from_provider(source)
        elif isinstance(source, (tuple, list)):
            cache_key, min_zoom, max_zoom, url, attribution, options = source
            self.map_source = MapSource(url=url, cache_key=cache_key,
                                        min_zoom=min_zoom, max_zoom=max_zoom,
                                        attribution=attribution, **options)
        elif isinstance(source, MapSource):
            self.map_source = source
        else:
            raise Exception("Invalid map source provider")
        self.zoom = clamp(self.zoom,
                          self.map_source.min_zoom, self.map_source.max_zoom)
        self.remove_all_tiles()
        self.trigger_update(True)