#!/usr/bin/env python2.7

'''
Aviron 7
sci-fi RTS retro/80's/8-bit style computer game, in Python, using Pygame and (Phil Hassey's) PGU

by Mike Kramlich
    started 2012 April 4 (approx. est.)
    revised 2016 June 25
'''

import math, os, random, sys

import pygame # 1.9.2
import pygame.font
import pygame.gfxdraw
from pygame.mixer import Sound
from pygame import Rect, Surface
import pygame.locals
import pgu # 0.18
from pgu import engine
from pgu import text as pgu_text

import groglib


class MyGame(engine.Game):
    def init(self):
        print 'MyGame.init()'
        advance_and_play_music(True)

    def tick(self):
        global tock, msgs
        clock.tick(MAX_FPS) #TODO should this be at end of loop instead?
        if not paused:
            tock += 1
            changed = False
            for th in things:
                changed = (th.tick() or changed)
            if count_civs() < 10 and groglib.rand_success(0.01): #TODO should not walk count civs each time, bad algo
                new_civ_on_ground()
                news('civ added to colony')
                changed = True
            if (tock % 250) == 0: #600
                random_ship_traffic_sky()
            if (tock % 100) == 0:
                msgs_kept = []
                for msg in msgs:
                    #print 'msg %s' % str(msg)
                    tock_created = msg[1]
                    if tock < (tock_created + 100):
                        msgs_kept.append(msg)
                    else:
                        changed = True
                msgs = msgs_kept
            if changed: self.state.repaint()

    def event(self, e):
        global debug, paused, show_interiors
        handled = False
        if e.type == MUSIC_VOL_RAISE:
            print 'MUSIC_VOL_RAISE handling by MyGame'
            pygame.time.set_timer(MUSIC_VOL_RAISE,0)
            pygame.mixer.music.set_volume(1.0)
            handled = True
        elif e.type == MUSIC_ENDED_EVENT:
            print 'MUSIC_ENDED_EVENT handling by MyGame'
            advance_and_play_music(False)
            handled = True
        elif e.type == LANDED_EVENT:
            print 'LANDED_EVENT handling by MyGame'
            #TODO see if the landing impacts cause harm to any civs or objects
            #handled = True
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_d and e.mod & pygame.KMOD_LSHIFT:
            debug = not debug
            handled = True
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_i and e.mod & pygame.KMOD_LSHIFT:
            show_interiors = not show_interiors
            handled = True
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
            paused = not paused
            handled = True
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_BACKQUOTE:
            advance_and_play_music(True)
            handled = True
        if not handled:
            handled = engine.Game.event(self,e)
        return handled


class MyState(engine.State):
    def paint(self, screen):
        screen.fill(colors['black']) # Empty Black Background

        pygame.draw.line(screen, colors['white'], (0,ground_y), (ww-1,ground_y), 1) # The Ground

        for th in things:
            th.draw(screen) # Entities: Ships, Creatures, Buildings, etc.
            th.draw_debug(screen) # just draw debug addons
            th.draw_focus(screen) # just draw focus addons

        draw_text(title, screen, centerinside=Rect(0,0,ww,50), fontname='title') # Game Title

        for i,msg in enumerate(msgs[-20:]): # Event Messages
            txt = msg[0]
            draw_text(txt, screen, pos=(10, 10 + i*20), fontname='messages')

        if debug:
            draw_text('tock %i' % tock, screen, pos=(400,10)) # Tock (Current Clock Time in the Game World)

        draw_text(music_playing_fpath, screen, pos=(500, 10), fontname='messages')

        if debug:
            for i,key in enumerate(sorted(counters.keys())): # Counter Stats
                v = counters[key]
                t = '%s = %i' % (key, v)
                draw_text(t, screen, pos=(ww-300, 25 + i*20), fontname='messages')
            
        pygame.display.flip()

    def event(self, e):
        global focused
        changed = False

        if e.type != pygame.MOUSEMOTION:
            print 'state event: %s (%s)' % (e, pygame.event.event_name(e.type))

        if e.type == pygame.KEYDOWN and e.key == pygame.K_q:
            pygame.event.post(pygame.event.Event(pygame.locals.QUIT))
            return
        elif e.type == pygame.MOUSEBUTTONDOWN:
            print 'mouse down at %s' % str(e.pos)
            mx,my = e.pos[0], e.pos[1]
            #TODO build list all things that overlap click pt & cycleselect thru
            th_ds = []
            for th in things:
                d = int(groglib.dist(mx,my, th.x,th.y)) #TODO use th's bounds
                th_ds.append( (d,th) )
            th_ds_sorted = sorted(th_ds, key=lambda x: x[0])
            focused = th_ds_sorted[0][1]
            changed = True
            print 'click changed focus to thing %s' % focused
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_TAB: # cycle focus to next thing
            print 'TAB handling'
            print 'focused %s; things.index(f) %i' %  (focused, (focused and (focused in things) and things.index(focused)) or -99)
            play_sound('focus-cycle')
            #print 'TAB e %s mod %s   KMOD_LSHIFT %s' % (dir(e), e.mod, str(pygame.KMOD_LSHIFT))
            rel = 1
            if e.mod & pygame.KMOD_LSHIFT:
                rel = -1
            i = None
            if focused in things:
                i = things.index(focused)
            oldi = i
            if i is None:
                i = -1
            i = i + rel
            if i >= len(things): i = 0
            elif i < 0: i = len(things) - 1
            if i >= 0 and i < len(things):
                focused = things[i]
            else:
                focused = None
            print 'oldi %s, rel %i, i %i, focused %s' % (oldi, rel, i, focused)
            changed = True
        else:
            if e.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                # is user input ev so only the focused Thing should handle now
                if focused:
                    changed = focused.event(e) or changed
            else: # it's a game model event, and so every Thing should hear
                for th in things:
                    changed = th.event(e) or changed
        if changed: self.repaint()


ALIGN_LEFT_TOP   = 0
ALIGN_MID_TOP    = 1
ALIGN_MID_MID    = 2
ALIGN_MID_BOTTOM = 3


class Thing:
    def __init__(self, name, color, x, y, w, h, align=ALIGN_MID_TOP, left=None, top=None):
        self.name = name
        self.color = color
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.align = align
        if not left:
            if self.align in (ALIGN_MID_TOP, ALIGN_MID_MID, ALIGN_MID_BOTTOM):
                #print 'thing %s %s' % (self, self.name)
                self.left = self.x - self.w / 2
            else: # assume ALIGN_LEFT_TOP
                self.left = self.x
        if not top:
            if self.align == ALIGN_MID_TOP:
                self.top = self.y
            elif self.align == ALIGN_MID_MID:
                self.top = self.y - self.h / 2
            elif self.align == ALIGN_MID_BOTTOM:
                self.top = self.y - self.h
            else: # assume ALIGN_LEFT_TOP
                self.top = self.y
        self.mov_dir = (0,0)
        self.acc_dir = (0,0)
        self.state = None
        self.debug_yrel = random.randrange(0,80)

    def set_x(self, x):
        dx = x - self.x
        self.x = x
        self.left = self.left + dx

    def set_y(self, y):
        dy = y - self.y
        self.y = y
        self.top = self.top + dy

    def set_xy(self, x, y):
        self.set_x(x)
        self.set_y(y)

    def chg_x(self, d):
        self.x = self.x + d
        self.left = self.left + d

    def chg_y(self, d):
        self.y = self.y + d
        self.top = self.top + d

    def chg_xy(self, dx, dy):
        self.x = self.x + dx
        self.y = self.y + dy
        self.left = self.left + dx
        self.top = self.top + dy

    #def draw(self, dest):
    def draw(self, dest, draw_base_xy=(0,0)):
        pygame.draw.rect(dest, self.color, (self.x, self.y, self.w, self.h), 1)

    def draw_debug(self, dest): pass

    def draw_focus(self, dest):
        if focused == self:
            #pygame.draw.rect(dest, colors['yellow'], (self.x-1, self.y-1, self.w+2, self.h+2), 1)
            pygame.draw.rect(dest, colors['yellow'], (self.left-1, self.top-1, self.w+2, self.h+2), 1)

    def tick(self): # return True if self's model state has changed such that it would need repaint
        return False

    def event(self, e): # return True if self's model state has changed such that it would need repaint
        return False


class Building(Thing):
    def __init__(self, name, x, y, w, h, color=None):
        if not color:
            color = colors['white']
        Thing.__init__(self, name, color, x, y, w, h, align=ALIGN_LEFT_TOP)

    def draw(self, dest):
        pygame.draw.rect(dest, self.color, (self.left, self.top, self.w, self.h), 1)


class Speech(Thing):
    def __init__(self, x, y, text='', tock_life=100):
        Thing.__init__(self, 'text', colors['white'], x, y, w=100, h=20)
        self.text = text
        self.tock_created = tock
        self.tock_life = tock_life

    def draw(self, dest):
        draw_text(self.text, dest, pos=(self.x, self.y), fontname='messages')

    def tick(self): # return True if self's model state has changed such that it would need repaint
        if tock >= self.tock_created + self.tock_life:
            things.remove(self)
            return True
        return False

class StoryOverlay(Thing):
    def __init__(self, w, h, text='', tock_life=100):
        x = ww/2 - w/2
        y = wh/2 - h/2
        Thing.__init__(self, 'text', colors['white'], x, y, w, h)
        self.text = text
        self.tock_created = tock
        self.tock_life = tock_life

    def draw(self, dest):
        r_border = Rect(self.x, self.y, self.w, self.h)
        dest.fill(colors['darkgray'],r_border)
        r_text = r_border.inflate(-20,-20)
        pgu_text.writewrap(dest, fonts['messages'], r_text, self.color, self.text, maxlines=None)

    def tick(self): # return True if self's model state has changed such that it would need repaint
        if tock >= self.tock_created + self.tock_life:
            things.remove(self)
            return True
        return False


class Billboard(Thing):
    def __init__(self, x, y, text='', refresh_tocks=200, sign_h=100, w=200, h=200, text_color=None):
        Thing.__init__(self, 'text', colors['white'], x, y, w, h, align=ALIGN_LEFT_TOP)
        self.refresh_tocks = refresh_tocks
        self.text = text
        self.text_choices = []
        self.fetch_new_text()
        if not text_color:
            text_color = colors['red']
        self.text_color = text_color
        self.sign_h = sign_h

    def fetch_new_text(self):
        self.text_choices = [
            'Remain Calm','Trust Noone','Keep Your Laser Handy','The Computer is your Friend',
            'Ignorance is Strength',"Peace Through War","Take Your Pills","Be Happy","Watch Out","Danger!",
            "Intruder Alert!","Stay Tuned","News at 11","Peace in Our Time","Nothing Lasts Forever",
            "Hate is Love","Silence is Now Mandatory","Coming Soon","Consult Your Doctor","Offer Not Valid Everywhere",
            "Happiness is a Warm Gun","The final voyage is now beginning","A long time ago in a galaxy far, far away...",
            "To boldy go where no man has gone before...","These are the voyages of the starship...",
            "Sorry Dave, I'm afraid I can't do that.", "Open the pod bay doors, HAL.","Do or do not. There is no try.",
            "This Space For Rent","It was the best of times, it was the worst of times...","A grand adventure awaits you!","Last call for Titanic. Passengers advised to board promptly.","It's rather depressing to be a hyper-intelligent billboard AI."]

    def draw(self, dest):
        l = self.left; t = self.top; w = self.w; h = self.h
        pole_w = 10
        pole_h = w - self.sign_h
        pygame.draw.rect(dest, self.color, (l+w/2-pole_w/2, t+self.sign_h, pole_w, pole_h), 0) # pole
        pygame.draw.rect(dest, self.color, (l, t, w, self.sign_h), 1) # sign board
        inset = 5
        pgu_text.writewrap(dest, fonts['billboard'], Rect(l+inset, t+inset, w-2*inset, self.sign_h-2*inset), self.text_color, self.text, maxlines=5)

    def tick(self): # return True if self's model state has changed such that it would need repaint
        if (tock % self.refresh_tocks) == 0:
            self.text = random.choice(self.text_choices)
            return True
        return False


class LightPost(Thing):
    def __init__(self, x, y, light_color=None, pole_h=20, light_radius=2, timing_offset=0):
        self.timing_offset = timing_offset
        self.flash_period = 10
        self.pole_h = pole_h
        self.light_radius = light_radius
        w = self.light_radius * 2
        h = self.pole_h + self.light_radius
        Thing.__init__(self, 'lamp', colors['white'], x, y, w, h, align=ALIGN_LEFT_TOP)
        if not light_color:
            light_color = colors['red']
        self.light_color = light_color
        #self.color will be color of the light post's pole
        self.flashing = True
        self.lit = True

    def draw(self, dest):
        x = self.x; y = self.y
        pygame.draw.line(dest,   self.color, (x,y), (x,y-self.pole_h), 1) # pole
        if self.flashing and self.lit:
            pygame.draw.circle(dest, self.light_color,   (x+1, y-self.pole_h), self.light_radius*2) # light

    def tick(self): # return True if self's model state has changed such that it would need repaint
        if self.flashing:
            if ((tock + self.timing_offset) % self.flash_period) == 0:
                self.lit = not self.lit
                return True
        return False


class Ship(Thing):
    def __init__(self, name, color, x, y, w, h):
        Thing.__init__(self, name, color, x, y, w, h, align=ALIGN_LEFT_TOP)
        self.mov_dir = None
        self.fuelmax = 2000
        self.fuel = self.fuelmax
        self.passengers = []
        self.disembark_passengers = False

    def add_passenger(self, passgr):
        x = 10 + len(self.passengers) * 10
        y = 12
        passgr.set_xy(x,y)
        self.passengers.append(passgr)

    def height(self): # is dynamic, takes into account current extend/retract state of landing gear
        return self.h

    def draw(self, dest):
        l = self.left; t = self.top; x = self.x; y = self.y; nw = self.nose_w
        # Ship's Name
        draw_text(self.name, dest, pos=(l + nw + 5, t + 30), color=self.color, fontname='shipname') 

    def event(self, e): # TODO shouldn't pass raw keyboard/mouse input events into here, instead the Game/State should translate into thing-specific semantic commands like (travel up, travel down, lower landing gear, fire guns, etc.)
        changed = False
        if e.type == pygame.KEYDOWN and e.key == pygame.K_w: # order ship to start moving Up
            if self.mov_dir != (0,-1) and self.fuel:
                self.mov_dir = (0,-1)
                play_sound('engine')
                changed = True
            elif self.mov_dir == (0,-1):
                self.mov_dir = None
                play_sound('engine')
                changed = True
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_s: # order ship to start moving Down
            if self.mov_dir != (0,1) and self.fuel:
                self.mov_dir = (0,1)
                play_sound('engine')
                changed = True
            elif self.mov_dir == (0,1):
                self.mov_dir = None
                play_sound('engine')
                changed = True
        elif e.type == LANDED_EVENT:
            print 'LANDED_EVENT evaled by ship %s %s' % (self.name, self)
            ship_landed = e.ship
            if ship_landed == self:
                if self.disembark_passengers:
                    pn = len(self.passengers)
                    if pn > 0:
                        print 'this ship landed so will disembark %i passengers' % pn
                        for p in self.passengers:
                            x_jitter = random.randrange(-10,11)
                            x = self.left + x_jitter
                            y = self.top + self.height()# -5
                            p.set_xy(x,y)
                            things.append(p)
                            changed = True
                        self.passengers = []
                        news('ship %s landed and disembarked %i passengers' % (self.name,pn))
                        play_sound('passengers-disembark')
            
        return changed

    def tick(self): # return True if self's model state has changed such that it would need repaint
        changed = False

        if hasattr(self,'npc'):
            if self.left+self.w < 0 or self.top+self.h < 0: # meaning, is offscreen (to left, or to top) #TODO do this right
                dbg('removing npc ship %s %s' % (self.name, self))
                things.remove(self)
                changed = True
                return changed

        if self.mov_dir is not None and self.fuel > 0:
            self.chg_xy(self.mov_dir[0], self.mov_dir[1])
            self.fuel -= 1
            cincr('ship fuel consumed')
            if self.top + self.height() >= above_ground_y: #TODO ugly way to do this, vuln
                new_top = above_ground_y - self.height()
                self.set_y(new_top)
                self.mov_dir = None
                play_sound('ship-landing')
                play_sound('engine')
                news('landed!')
                #TODO also handle case where landing gear was up and entire ship bottom could crush civs not just LG
                lgy = self.top + self.height() #TODO the X's on following lines are not calc right!
                #TODO base following x,y,r tuples on where the two LG feet are currently
                g0x = self.x; g0y = lgy; g0r = 20 # these are the x,y,r of the two landing gear impact points
                g1x = self.x; g1y = lgy; g1r = 20 # any civs near either impact points will be killed or maimed
                #TODO the following event is not finished populating the 'impacts' value:
                ev = pygame.event.Event(LANDED_EVENT,{'ship':self,'impacts':[(g0x,g0y,g0r),(g1x,g1y,g1r)]})#TODO change impacts to rects not circles
                pygame.event.post(ev)
            changed = True

        return changed


class LandingField(Thing):
    'this is a game entity, but not a single direct physical thing'
    def __init__(self, name, x, y, w, h):
        Thing.__init__(self, name, colors['white'], x, y, w, h, align=ALIGN_MID_TOP, left=None, top=None)
        self.lightposts = []

    def draw(self, dest):
        pass # no-op because not visible

    def event(self, e):
        changed = False
        if e.type == LANDED_EVENT:
            print 'LandingField %s received LANDED_EVENT regarding ship %s' % (self.name, e.ship)
            for lp in self.lightposts:
                lp.flashing = lp.lit = False
        return changed


class GeometryShip(Ship):
    def __init__(self, name, x, y, color=None, pts=[(0,0),(2,0),(2,1),(0,1)], scale=1.0):
        if not color:
            color = colors['white']
        w = 0
        h = 0
        self.pts = pts
        self.pts2 = []
        for i in range(len(self.pts)):
            pt0 = self.pts[i]
            x0 = int(float(pt0[0]) * scale)
            y0 = int(float(pt0[1]) * scale)
            self.pts2.append( (x0,y0) )
            #print 'geo ship %s pts2: %i,%i' % (name, x0,y0)
            if x0 > w:
                w = x0
            if y0 > h:
                h = y0
        #print 'geo ship %s w,h: %i,%i' % (name, w,h)
        # we've now calculated the w and h based on the pts given, and scaled, (cached into pts)
        Ship.__init__(self, name, color, x, y, w, h)

    def draw(self, dest):
        l = self.left; t = self.top; x = self.x; y = self.y; w = self.w; h = self.h
        for i in range(len(self.pts2)):
            j = i + 1
            if j >= len(self.pts2):
                j = 0
            pt0 = self.pts2[i]
            pt1 = self.pts2[j]
            x0 = l + pt0[0]
            y0 = t + pt0[1]
            x1 = l + pt1[0]
            y1 = t + pt1[1]
            #print 'geo draw %s to %s' % (pt0, pt1)
            #print 'geo draw %i,%i, to %i,%i' % (x0,y0,x1,y1)
            pygame.draw.line(dest, self.color, (x0,y0), (x1,y1), 1)
        # Passengers
        for p in self.passengers:
            #if self.name == 'Vyit': print '%i: drawing pass' % tock
            p.draw(dest, (l, t))
        # Ship's Name
        draw_text(self.name, dest, pos=(l+w/2, t+h/2), color=self.color, fontname='shipname') 

    def add_passenger(self, passgr):
        print 'adding pass to geoship %s' % self.name
        l = self.left; t = self.top; w = self.w; h = self.h; ps = self.passengers; pq = len(ps)
        ps.append(passgr)
        if pq < 4:
            max_q_per_row = 2
        else:
            max_q_per_row = int(math.ceil(math.sqrt(pq)))
        row = 0
        col = 0 
        bx = w / 2
        by = h / 2
        ss = ''
        for p in ps:
            if col >= max_q_per_row:
                row += 1
                col = 0
            x = bx + col * 15 #TODO should consider indiv w & h of each pass 
            y = by + row * 15
            ss += ' %i,%i' % (x, y)
            passgr.set_xy(x,y)
            col += 1
        print ss


class GanymedeClassShip(Ship):
    LGPOSY_RANGE = (0,30)
    lgh = 50

    def __init__(self, name, color, x, y, w=260):
        Ship.__init__(self, name, color, x, y, w, 50)
        self.lg_state = None
        self.lg_dir = None
        self.lg_posy = 0
        self.nose_w = 60
        self.hull_w = self.w - self.nose_w # ie, 200 = 260 - 60
        self.hull_h = 50

    def height(self): # is dynamic, takes into account current extend/retract state of landing gear
        return 0 + self.lg_posy + self.lgh

    def draw(self, dest):
        l = self.left; t = self.top; x = self.x; y = self.y; nw = self.nose_w
        # Engine Thrust Plumes
        if self.mov_dir:
            pw = 25
            ph = 50
            px = l + nw + self.hull_w/2 - pw/2
            #TODO add support for thrust right, plume left
            #TODO add support for hovering aka 'not-landed & Y is constant' (regardless of X mov_dir)
            if self.mov_dir == (0,1): # thrust down via plume on top pointed up
                py = t - ph + 15
            elif self.mov_dir == (-1,0): # thrust left via plum on right pointed right
                pw = 50
                ph = 25
                px = l + nw + self.hull_w
                py = t + self.hull_h/2 - ph/2
            else: # assume mov_dir == (0,-1) aka thrust up via plume on bottom pointed down
                py = t + self.h - 15
            c = colors[ random.choice( ('red','orange'))]
            pygame.draw.ellipse(dest, c, (px, py, pw, ph))
        # Hull
        pygame.draw.rect(dest, self.color, (l+nw, t, self.hull_w, self.hull_h), 1)
        if show_interiors:
            # Fuel Tank
            tankw = 80
            tankh = 30
            tankx = l + self.nose_w + 60
            tanky = t + 10
            pygame.draw.rect(dest, self.color,        (tankx, tanky,               tankw, tankh), 1)
            # Fuel in Fuel Tank
            if self.fuel:
                fuelh = int( (tankh-2) * (float(self.fuel) / float(self.fuelmax)) )
                pygame.draw.rect(dest, colors['darkmagenta'], (tankx+1, tanky+tankh-1-fuelh, tankw-2, fuelh), 0)
        # Nose Cone, Bridge, Cockpit
        pygame.gfxdraw.aatrigon(dest, l,    t+self.h/2,
                                      l+nw, t,
                                      l+nw, t+self.h, self.color)
        # Window in Cockpit
        pygame.gfxdraw.aatrigon(dest, l+nw-35, t+20,
                                      l+nw-5,  t+10,
                                      l+nw-5,  t+20, colors['white'])
        # Landing Gear - twin, same appearance, but one near front of ship and one near back, same X insets
        lginset = 20
        lgw = 20
        lgy = t + self.h - self.lgh + self.lg_posy # 0 is fully retracted/stowed
        c = self.color
        lgxs = [l + nw + lginset,
                l + nw + self.hull_w - lginset - lgw]
        for lgx in lgxs: # draw each of the 2 landing gear
            pygame.draw.rect(dest, c, (lgx, lgy, lgw, self.lgh), 1)
            feeth = 10
            feetwextra = 10
            pygame.draw.rect(dest, c, (lgx-feetwextra, lgy+self.lgh-feeth, lgw+2*feetwextra, feeth), 1) # draw foot
        if show_interiors:
            # Passengers
            for p in self.passengers:
                p.draw(dest, (l+nw, t))
        # Ship's Name
        draw_text(self.name, dest, pos=(l + nw + 5, t + 30), color=self.color, fontname='shipname') 

    def event(self, e): # TODO shouldn't pass raw keyboard/mouse input events into here, instead the Game/State should translate into thing-specific semantic commands like (travel up, travel down, lower landing gear, fire guns, etc.)
        changed = Ship.event(self, e) #TODO should also return handled, make retval a tuple
        if e.type == pygame.KEYDOWN and e.key == pygame.K_i: # order landing gear to retract
            if self.lg_state != 'moving' or self.lg_dir != 'up':
                self.landing_gear('moving','up')
                play_sound('landing-gear')
                changed = True
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_k: # order landing gear to extend
            if self.lg_state != 'moving' or self.lg_dir != 'down':
                self.landing_gear('moving','down')
                play_sound('landing-gear')
                changed = True
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_l:
            if self.lg_state is not None:
                self.landing_gear(None,None)
                changed = True
        return changed

    def tick(self):
        changed = Ship.tick(self)
        if self.lg_state == 'moving':
            if self.lg_dir == 'down':
                if self.lg_posy < self.LGPOSY_RANGE[1]:
                    self.lg_posy = self.lg_posy + 1
                    changed = True
            elif self.lg_dir == 'up':
                if self.lg_posy > self.LGPOSY_RANGE[0]:
                    self.lg_posy = self.lg_posy - 1
                    changed = True
        return changed

    def landing_gear(self, newstate, newdir):
        self.lg_state = newstate
        self.lg_dir = newdir


class Humanoid(Thing):
    #dirs = [(-1,-1), (-1,0), (-1,1), (0,-1), (0,0), (0,1), (1,-1), (1,0), (1,1)]
    dirs = [(-1,0), (0,0), (1,0)]
    dir = (0,0)
    wanders = True
    flees = False
    hunts = False
    feared_classes = []
    not_feared_classes = []
    nearest_fear = None
    nearest_fear_dist = None
    hunted_classes = []
    not_hunted_classes = []
    nearest_hunted = None
    nearest_hunted_dist = None

    def event(self, e):
        pass

    def does_fear(self, it):
        if it is self: return False
        feared = False
        for cl in self.feared_classes:
            if isinstance(it,cl):
                feared = True
                break
        if feared:
            for cl in self.not_feared_classes:
                if isinstance(it,cl):
                    feared = False
                    break
        return feared

    def does_hunt(self, it): #TODO refactor DRY between this and does_fear()
        if it is self: return False
        hunted = False
        for cl in self.hunted_classes:
            if isinstance(it,cl):
                hunted = True
                break
        if hunted:
            for cl in self.not_hunted_classes:
                if isinstance(it,cl):
                    hunted = False
                    break
        return hunted

    def tick(self):
        changed = False

        if self.wanders:
            if groglib.rand_success(0.1): # 20% chance of changing movement heading
                self.dir = random.choice(self.dirs)

        if self.flees:
            nearest_fear = None
            nearest_fear_dist = None
            for th in things:
                if th is self: continue
                if self.does_fear(th):
                    d = int(groglib.dist(self.x,self.y, th.x,th.y))
                    if not nearest_fear:
                        nearest_fear = th
                        nearest_fear_dist = d
                    else:
                        if d < nearest_fear_dist:
                            nearest_fear = th
                            nearest_fear_dist = d
            prev_nf = self.nearest_fear
            prev_nfd = self.nearest_fear_dist
            self.nearest_fear = nearest_fear
            self.nearest_fear_dist = nearest_fear_dist
            if prev_nf is not self.nearest_fear or prev_nfd != self.nearest_fear_dist:
                changed = True
            if nearest_fear:
                xrel = cmp(nearest_fear.x, self.x)
                flee_xrel = 0
                if xrel > 0:
                    flee_xrel = -1
                elif xrel < 0:
                    flee_xrel = 1
                else: # xrel == 0, so pick a random dir to flee
                    flee_xrel = random.choice( [-1,1] )
                dir_prev = self.dir
                self.dir = (flee_xrel,0)
                if dir_prev != self.dir:
                    changed = True

        if self.hunts:
            nearest_hunted = None
            nearest_hunted_dist = None
            for th in things:
                if th is self: continue
                if self.does_hunt(th):
                    d = int(groglib.dist(self.x,self.y, th.x,th.y))
                    if not nearest_hunted:
                        nearest_hunted = th
                        nearest_hunted_dist = d
                    else:
                        if d < nearest_hunted_dist:
                            nearest_hunted = th
                            nearest_hunted_dist = d
            prev_nh = self.nearest_hunted
            prev_nhd = self.nearest_hunted_dist
            self.nearest_hunted = nearest_hunted
            self.nearest_hunted_dist = nearest_hunted_dist
            if prev_nh is not self.nearest_hunted or prev_nhd != self.nearest_hunted_dist:
                changed = True
            if nearest_hunted:
                xrel = sign(nearest_hunted.x - self.x)
                move_xrel = 0
                if xrel > 0:
                    move_xrel = 1
                elif xrel < 0:
                    move_xrel = -1
                else: # xrel == 0, so pick a random dir to flee
                    move_xrel = random.choice( [-1,1] )
                dir_prev = self.dir
                self.dir = (move_xrel,0)
                if dir_prev != self.dir:
                    changed = True

        if self.dir != (0,0):
            self.chg_xy(self.dir[0], self.dir[1])
            x, y = clamp_to_world(self.x, self.y)
            self.set_xy(x,y)
            changed = True

        return changed


class Human(Humanoid):
    def __init__(self, name, color, x, y, w, h):
        Humanoid.__init__(self, name, color, x, y, w, h, align=ALIGN_MID_BOTTOM)
        self.sayings = []
        self.saychance = 0.005
        self.body_h = (h * 2) / 3
        
    def draw(self, dest, draw_base_xy=(0,0)):
        c = self.color
        x = self.x + draw_base_xy[0]
        y = self.y + draw_base_xy[1]
        bh = self.body_h
        pygame.draw.circle(dest, c, (x, y-bh), 2) # head
        pygame.draw.line(dest,   c, (x, y), (x, y-bh), 1) # torso & legs

    def draw_debug(self, dest):
        if debug:
            w = self.wanders and 'W' or ''
            f = self.flees and 'F' or ''
            h = self.hunts and 'H' or ''
            snf = self.nearest_fear
            snh = self.nearest_hunted
            nf = snf and ('%s-%s(%i,%i) ' % (snf.name, str(id(snf))[-4:], snf.x, snf.y)) or ''
            nfd = snf and ('%i ' % self.nearest_fear_dist) or ''
            nh = snh and ('%s-%s(%i,%i) ' % (snh.name, str(id(snh))[-4:], snh.x, snh.y)) or ''
            nhd = snh and ('%i ' % self.nearest_hunted_dist) or ''
            debugtxt = '%s%s%s%s%s%s%s %s' % (w, f, nf, nfd, h, nh, nhd, self.dir)
            y =  self.y - self.h - 20 - self.debug_yrel
            draw_text(debugtxt,  screen, pos=(self.x,y), fontname='debug') # Debug Info
            draw_text(self.name, screen, pos=(self.x,y-12), fontname='debug') # Debug Info

    def get_sayings(self):
        return self.sayings

    def get_saychance(self):
        return self.saychance

    def tick(self):
        changed = Humanoid.tick(self)
        if len(self.get_sayings()):
            if groglib.rand_success(self.get_saychance()):
                speech = random.choice(self.get_sayings())
                yvar = random.randrange(0,51)
                tl = random.randrange(40,90)
                things.append(Speech(self.x, self.y-self.body_h-(10+yvar), speech, tock_life=tl))
                changed = True
        return changed


class Civ(Human):
    def __init__(self, x, y, name=None, color=None, h=None):
        if not name:
            name = 'civ'
        w = 5
        if not h:
            h = random.randrange(10,12)
        if not color:
            color = colors['white']
        Human.__init__(self, name, color, x, y, w, h)
        self.sayings = ["derp",]
        self.saychance = 0.002

    def tick(self):
        changed = Human.tick(self)
        before_flees = self.flees
        now_flees = False
        for th in things:
            if self.does_fear(th):
                now_flees = True
                break
        if not before_flees and now_flees:
            self.flees = True
            news('civ aware of alien and will flee')
            changed = True
        elif before_flees and not now_flees:
            self.flees = False
            news('civ thinks no more aliens so will no longer flee')
            changed = True
        if not self.flees:
            if not self.wanders:
                news('civ will wander')
                changed = True
            self.wanders = True
        else: self.wanders = False
        return changed

    def get_sayings(self):
        if self.flees:
            return ["OMG!","Run for your lives!","We're doomed!","Help!","Holy fuck!"]
        else: return self.sayings

    def get_saychance(self):
        if self.flees:
            return 0.01
        else: return self.saychance

class Avatar(Human):
    def __init__(self, x, y, name=None, color=None, h=11):
        if not name:
            name = 'PC'
        w = 5
        if not color:
            color = colors['yellow']
        Human.__init__(self, name, color, x, y, w, h)
        self.sayings = []
        self.saychance = 0.0
        self.wanders = False
        self.hunts = False
        self.flees = False

    def event(self, e): # TODO shouldn't pass raw keyboard/mouse input events into here, instead the Game/State should translate into thing-specific semantic commands like (travel up, travel down, lower landing gear, fire guns, etc.)
        changed = False
        if e.type == pygame.KEYDOWN and e.key == pygame.K_d: # order him to walk east
            if self.dir != (1,0):
                self.dir = (1,0)
                changed = True
                print 'pc will walk east'
            else:
                self.dir = (0,0)
                changed = True
                print 'pc will stop walking east'
        if e.type == pygame.KEYDOWN and e.key == pygame.K_a: # order him to walk west
            if self.dir != (-1,0):
                self.dir = (-1,0)
                changed = True
                print 'pc will walk west'
            else:
                self.dir = (0,0)
                changed = True
                print 'pc will stop walking west'
        return changed

class Marine(Human):
    attacks = True

    def __init__(self, x, y, name=None, color=None, h=None):
        w = 5
        if not h:
            h = random.randrange(10,12)
        if not color:
            c = colors['cyan']
        if not name:
            name = 'Pvt. %s' % give_last_name()
        Human.__init__(self, name, c, x, y, w, h)
        self.wanders = True
        self.flees = False
        self.hunts = False
        self.sayings = ["'Who's your daddy?'",
                        "This feels right.",
                        "That's right.",
                        "BOOYA!",
                        "Saddle up, boys!",
                        "I need to shoot something.",
                        "Any alien gets near me is gonna go BOOM real fast.",
                        "'I came to chew gum and kick ass but I'm all out of gum.'",
                        "'Another a bug hunt?'"]

    def draw(self, dest, draw_base_xy=(0,0)):
        c = self.color
        bh = self.body_h
        x = self.x + draw_base_xy[0]
        y = self.y + draw_base_xy[1]
        pygame.draw.circle(dest, c, (x, y-bh), 2) # head
        pygame.draw.line(dest,   c, (x, y), (x, y-bh), 1) # torso & legs
        guny = y - bh / 2
        pygame.draw.line(dest, colors['black'], (x-3, guny-1), (x+4, guny-1), 1) # rifle: horiz line midbody
        pygame.draw.line(dest, colors['white'], (x-2, guny),   (x+5, guny), 1) # rifle: horiz line midbody

    def tick(self):
        changed = Human.tick(self)

        before_hunts = self.hunts
        now_hunts = False
        for th in things:
            if self.does_hunt(th):
                now_hunts = True
                break
        if not before_hunts and now_hunts:
            self.hunts = True
            news('marine %s aware of alien and will hunt' % self.name)
            changed = True
        elif before_hunts and not now_hunts:
            self.hunts = False
            news('marine %s thinks no more aliens so will no longer hunt' % self.name)
            changed = True
        if not self.hunts:
            if not self.wanders:
                news('marine %s will wander' % self.name)
                changed = True
            self.wanders = True
        else:
            self.wanders = False
            self.flees = False

        def in_attack_range(me, other):
            return groglib.dist(me.x,me.y, other.x,other.y) <= 15

        if self.attacks:
            for th in things: #TODO just iter through all aliens
                if th is self: continue
                if isinstance(th,Alien) and not isinstance(th,Gigan):
                    if in_attack_range(self,th):
                        chance = isinstance(th,AlienEgg) and 0.9 or 0.4
                        victim = th.name
                        if groglib.rand_success(chance):
                            news('marine %s killed %s! *BOOYA!*' % (self.name,victim))
                            cincr('%ss killed by marines' % victim)
                            things.remove(th) #TODO send event to victim telling it he's been attacked/killed
                            play_sound('shoot-once')
                            if isinstance(th,AlienEgg):
                                play_sound('alien-egg-killed')
                            elif isinstance(th,AlienAdult):
                                play_sound('alien-adult-killed')
                        else:
                            news('marine %s attacked %s but it survived!' % (self.name,victim))
                            cincr('%ss survived attacks by marines' % victim)
                            play_sound('shoot-twice')
                        changed = True
                        break
        return changed


class Alien(Humanoid):
    def __init__(self, name, color, x, y, w, h):
        Humanoid.__init__(self, name, color, x, y, w, h, align=ALIGN_MID_BOTTOM)
Marine.hunted_classes = [Alien,]


class AlienEgg(Alien):
    wanders = False
    attacks = False
    H = 6

    def __init__(self, x, y, name='alien egg', color=None, w=None, h=None, hatch_ticks=None):
        if not w:
            w = random.randrange(7,9)
        if not h:
            h = random.randrange(self.H-1, self.H+2)
        if not color:
            color = colors['darkgreen']
        Alien.__init__(self, name, color, x, y, w, h)
        self.created = tock
        if not hatch_ticks:
            hatch_ticks = random.randrange(500,600)
        self.hatch_ticks = hatch_ticks

    def ready_to_hatch(self):
        return (tock - self.created) >= self.hatch_ticks

    def may_hatch_soon(self):
        return (tock - self.created) >= (self.hatch_ticks - 50)

    def draw(self, dest, draw_base_xy=(0,0)):
        left = self.left + draw_base_xy[0]
        top = self.top + draw_base_xy[1]
        c = self.may_hatch_soon() and colors['yellow'] or self.color
        pygame.draw.ellipse(dest, c, (left, top, self.w, self.h))

    def tick(self):
        changed = Alien.tick(self)
        if self.ready_to_hatch() and groglib.rand_success(0.05):
            things.append( AlienAdult(self.x, self.y))
            things.remove(self)
            cincr('alien eggs hatched')
            news('egg hatched into alien adult!')
            play_sound('alien-egg-hatch')
            changed = True
        return changed


class AlienAdult(Alien):
    attacks = True
    egglayer = True
    H = 27#24#18
    pupil_moves = False

    def __init__(self, x, y, name='alien', color=None, w=None, h=None):
        if not color:
            color = colors['green']
        if not w: w = self.H / 3
        if not h: h = self.H
        Alien.__init__(self, name, color, x, y, w, h)
        self.pupil_x_offset = 0
        self.pupil_x_offset_dir = +1
        self.pupil_x_offset_range = (-1,1)

    def draw(self, dest, draw_base_xy=(0,0)):
        c = self.color
        x = self.x + draw_base_xy[0]
        y = self.y + draw_base_xy[1]
        # body/trunk:
        pygame.gfxdraw.filled_trigon(dest, x-self.w/2, y,
                                           x,          y-self.h,
                                           x+self.w/2, y, c)
        bw     = self.w / 3
        ew, eh = bw,   bw*2 # eyeball
        pw, ph = ew/3, eh/3 # pupil
        ex, ey = x - (ew/2), y - (self.h * 0.7)
        px, py = x - (pw/2), y - (self.h * 0.6)
        px = px + self.pupil_x_offset
        pygame.draw.ellipse(dest, colors['white'], (ex, ey, ew, eh)) # eyeball
        pygame.draw.ellipse(dest, colors['black'], (px, py, pw, ph)) # pupil

    def draw_debug(self, dest, draw_base_xy=(0,0)):
        if debug:
            x = self.x + draw_base_xy[0]
            y = self.y + draw_base_xy[1]
            y = y - self.h - 20 - self.debug_yrel
            draw_text('%s-%s' % (self.name,str(id(self))[-4:]), screen, pos=(x,y), fontname='debug') # Debug Info

    def draw_focus(self, dest, draw_base_xy=(0,0)):
        if focused == self:
            left = self.left + draw_base_xy[0]
            top = self.top + draw_base_xy[1]
            pygame.draw.rect(dest, colors['yellow'], (left-1, top-1, self.w+2, self.h+2), 1)

    def tick(self):
        changed = Humanoid.tick(self)

        if self.pupil_moves and not (tock % 4):
            # eye pupil X movement back-and-forth
            nx = self.pupil_x_offset + self.pupil_x_offset_dir
            if self.pupil_x_offset_dir > 0:
                if nx > self.pupil_x_offset_range[1]:
                    nx = self.pupil_x_offset_range[1]
                    self.pupil_x_offset_dir = -1
            else: # dir is negative
                if nx < self.pupil_x_offset_range[0]:
                    nx = self.pupil_x_offset_range[0]
                    self.pupil_x_offset_dir = +1
            self.pupil_x_offset = nx

        def in_attack_range(alien, civ):
            return groglib.dist(alien.x,alien.y, civ.x,civ.y) <= 15
        if self.attacks:
            for th in things: #TODO just iter through all humans
                if th is self: continue
                if isinstance(th,(Civ,Avatar)) and not isinstance(th,Marine):
                    if in_attack_range(self,th):
                        if groglib.rand_success(0.9):
                            news('alien killed %s!' % th.name)
                            if isinstance(th,Civ): cincr('civs killed by aliens')
                            things.remove(th) #TODO send event to victim telling it he's been attacked/killed
                            play_sound('alien-kills-human')
                            if self.egglayer and groglib.rand_success(0.9):
                                lay_egg(self.x,self.y)
                        else:
                            news('alien attacked %s but he survived!' % th.name)
                            if isinstance(th,Civ): cincr('civs survived attacks by aliens')
                        changed = True
                        break
                if isinstance(th,Marine):
                    if in_attack_range(self,th):
                        if groglib.rand_success(0.4):
                            news('alien killed marine %s!' % th.name)
                            cincr('marines killed by aliens')
                            things.remove(th) #TODO send event to victim telling it he's been attacked/killed
                            play_sound('alien-kills-human')
                            if self.egglayer and groglib.rand_success(0.6):
                                lay_egg(self.x,self.y)
                        else:
                            news('alien attacked marine %s but he survived!' % th.name)
                            cincr('marines survived attacks by aliens')
                        changed = True
                        break
        return changed
Civ.feared_classes = [AlienAdult,]


class Gigan(AlienAdult):
    wanders = False
    attacks = False
    egglayer = False
    pupil_moves = True

    def __init__(self, x, y, w, h, name='Gigan', color=None):
        if not color:
            color = colors['darkgreen']
        AlienAdult.__init__(self, x, y, name=name, w=w, h=h, color=color)
        self.pupil_x_offset_range = (-20,20)
Civ.not_feared_classes = [Gigan,]
Marine.not_hunted_classes = [Gigan,]


def new_civ_on_ground():
    x = random.randrange(0,ww)
    y = above_ground_y
    p = Civ(x, y) # civilian, NPC, person, human, colonist
    things.append(p)
    cincr('civs added to colony')
    return p




def count_civs():
    n = 0
    for th in things:
        if isinstance(th,Civ):
            n += 1
    return n

def news(txt):
    global msgs
    msg = (txt, tock)
    msgs.append(msg)
    if len(msgs) > MAX_MSGS:
        msgs = msgs[-MAX_MSGS:]

def newslog(msg):
    print msg
    news(msg)

def dbg(msg):
    print msg

def clamp_to_world(x, y): #TODO need ver that takes into account collision bounding boxes too
    if x >= ww: x = ww - 1
    elif x < 0: x = 0
    if y >= wh: y = wh - 1
    elif y < 0: y = 0
    return x, y

def cincr(key, qty=1):
    old = 0
    if key in counters:
        old = counters[key]
    counters[key] = old + qty

def sign(x):
    return cmp(x,0)

def news_incr(msg):
    news(msg)
    cincr(msg)

def lay_egg(x, y):
    things.append( AlienEgg(x, y))
    news_incr('egg laid')
    play_sound('alien-egg-lay')

def advance_and_play_music(rand=False):
    global music_index, music_playing_fpath
    print 'advance_and_play_music %s' % rand
    if not music_enabled: return
    if len(music_list) == 0: return
    if rand:
        music_index = random.randrange(0,len(music_list))
    else:
        music_index += 1
        if music_index >= len(music_list):
            music_index = 0
    musicfn = music_list[music_index]
    music_playing_fpath = fpath = musicfn
    pygame.mixer.music.stop()
    try:
        print 'loading music: %s' % fpath
        pygame.mixer.music.load(fpath)
        pygame.mixer.music.set_volume(1.0)
        print 'playing music: %s' % fpath
        pygame.mixer.music.play()
    except RuntimeError, e: # docs say catch RE in order to catch:  pygame.error, message
        print 'error doing music load %s: %s' % (fpath, e)

def give_last_name():
    global last_names_dex
    last_names_dex += 1
    if last_names_dex >= len(last_names):
        last_names_dex = 0
    return last_names[last_names_dex]

def random_ship_traffic_sky():
    #TODO fire event when this ship leaves the screen edge, then on that event handler, delete the ship
    q = random.randrange(0,4)
    cns = ('gray','lightgray','red','blue','darkblue','green','darkgreen','cyan','darkcyan','magenta','darkmagenta')
    for i in range(q):
        x = ww#800 + random.randrange(0,300) #TODO should start offscreen right, then move into view moving left
        y = 50 + random.randrange(0,450)
        w = 210 + random.randrange(0,70)
        cn = random.choice(cns)
        shiptypes = ('Ganymede','Neyn','Ryvan')
        st = random.choice(shiptypes)
        if st == 'Ganymede':
            c = colors[cn]
            ship = GanymedeClassShip('Roanoke', c, x, y, w) #TODO random name; random color
            ship.disembark_passengers = True
            for ic in range( random.randrange(0,10)):
                ship.add_passenger( Civ(0,0))
            things.append(ship)
        elif st == 'Neyn':
            scale = float(random.randrange(15,46))
            ship = make_Neyn(x,y,cn,scale)
        else: # st == 'Ryvan'
            scale = float(random.randrange(20,26))
            ship = make_Ryvan(x,y,cn,scale)
        ship.npc = True # needed to make ship cease once flies off-screen
        ship.mov_dir = (-1,0) #TODO have dir chosen rndly, could start offscr right mov left, or, offscr left mov right

def init_colors():
    global colors
    colors = {}
    co = colors
    co['white']      = (255,255,255)
    co['lightgray']  = (190,190,190)
    co['gray']       = (127,127,127)
    co['darkgray']   = ( 63, 63, 63)
    co['black']      = (  0,  0,  0)
    co['red']        = (255,  0,  0)
    co['orange']     = (255,127,  0)
    co['green']      = (  0,140,  0)
    co['darkgreen']  = (  0, 80,  0)
    co['blue']       = (  0,  0,255)
    co['darkblue']   = (  0,  0,127)
    co['cyan']       = (  0,255,255)
    co['darkcyan']   = (  0,127,127)
    co['yellow']     = (255,255,  0)
    co['darkyellow'] = (127,127,  0)
    co['magenta']    = (255,  0,255)
    co['darkmagenta']= (127,  0,127)

def init_fonts():
    global fonts
    fonts = {}
    fn = 'courier new, arial, verdana, arialblack, futura, impact, optima, arial, courier' # None Arial Futura
    fn = 'Courier New'
    #for f in pygame.font.get_fonts(): print f
    #sys.exit(1)
    fn = pygame.font.get_default_font()
    fn = None
    pygame.font.init()
    fnt = pygame.font.SysFont
    fnt = pygame.font.Font
    fonts['debug']    = fnt(fn,10)#'Arial', 10)
    fonts['default']  = fnt(fn,16)#'Arial', 16)
    fonts['messages'] = fnt(fn,16)#'Arial', 16)
    fonts['shipname'] = fnt(fn,10)#'Arial', 10)
    fonts['title']    = fnt(fn,50)#'Arial', 50)
    fonts['billboard']  = fnt(fn,20)#'Futura', 20)

def init_sounds():
    global sounds
    pygame.mixer.init()
    sounds = {}
    sounds['alien-egg-hatch'] = Sound('audio/FROG.wav')
    sounds['alien-egg-lay'] = Sound('audio/briefcs1.wav')
    sounds['alien-kills-human'] = Sound('audio/pit.wav')
    sounds['engine'] = Sound('audio/deton-bomb.wav')
    sounds['focus-cycle'] = Sound('audio/Select.wav')
    sounds['landing-gear'] = Sound('audio/SpaceLaunch.wav')
    sounds['passengers-disembark'] = Sound('audio/car_door.wav')
    sounds['ship-landing'] = Sound('audio/menu_blip.wav')
    sounds['shoot-once'] = Sound('audio/player_shot.wav')
    sounds['shoot-twice'] = Sound('audio/firing_infantry.wav')
    sounds['alien-egg-killed'] = Sound('audio/chomp.wav')
    sounds['alien-adult-killed'] = Sound('audio/crunch.wav')

def play_sound(name):
    sounds[name].play()

def draw_text(text, destsurface, pos=None, color=None, antialias=True, fontname=None, centerinside=None):
    if not color:
        color = colors['white']
    shadow_color = colors['black']
    if color == colors['black']:
        shadow_color = colors['darkgray']
    if not fontname:
        font = fonts['default']
    else:
        font = fonts[fontname]
    shadow_img = font.render(text, antialias, shadow_color)
    text_img = font.render(text, antialias, color)
    if pos:
        x = pos[0]
        y = pos[1]
    elif centerinside:
        if isinstance(centerinside,Rect):
            l = centerinside.left
            t = centerinside.top
            w = centerinside.width
            h = centerinside.height
        else:
            l = centerinside[0]
            t = centerinside[1]
            w = centerinside[2]
            h = centerinside[3]
        #x = centerinside[0] + centerinside[2]/2 - text_img.get_width()/2
        #y = centerinside[1] + centerinside[3]/2 - text_img.get_height()/2
        x = l + w/2 - text_img.get_width()/2
        y = t + h/2 - text_img.get_height()/2
    destsurface.blit(shadow_img, (x+1,y+1))
    destsurface.blit(text_img, (x,y))

def app_exit_cleanup():
    pygame.mixer.music.stop()
    pygame.mixer.stop()
    pygame.event.clear()
    pygame.quit()


def main():
    global clock
    clock = pygame.time.Clock()
    #pygame.time.set_timer(MUSIC_VOL_RAISE,2000)
    try:
        game.run(mainstate,screen)
    except:
        app_exit_cleanup()
        raise


pygame.init() 

# load and specify the app icon (shown in dock and task switchers; so as to not shown the default Pygame snake-biting-controller logo):
appicon = pygame.Surface((32,32))
appicon.set_colorkey((0,0,0)) # black in this surf sh. be treated transparent
rawicon = pygame.image.load('appicon.bmp') # must be 32x32, black is trans
# in Gimp i made a 32x32 RGB image, saved as xcf, saved copy as .bmp with 24bit (8-8-8) format
for i in range(0,32):
    for j in range(0,32):
        appicon.set_at((i,j), rawicon.get_at((i,j)))
pygame.display.set_icon(appicon) # must be called before set_mode


modes_avail = pygame.display.list_modes()
print modes_avail
best_size = modes_avail[0]
print 'best window size: ' + str(best_size)
used_size = (1366,720) # you may need to tweak this to fit your avail screen space #TODO make more robust/responsive
ww = used_size[0]
wh = used_size[1]
#screen = pygame.display.set_mode(used_size, pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF)
screen = pygame.display.set_mode(used_size, pygame.HWSURFACE | pygame.DOUBLEBUF)
print 'used window size: ' + str(used_size)

title = 'AVIRON 7'
pygame.display.set_caption(title)
MAX_FPS = 60
tock = 0

MUSIC_VOL_RAISE = pygame.USEREVENT+1
LANDED_EVENT = pygame.USEREVENT+2
MUSIC_ENDED_EVENT = pygame.USEREVENT+3

colors = None
init_colors()

fonts = {}
init_fonts()

sounds = {}
init_sounds()

counters = {}

with file('data/person_lastnames.txt') as f:
    last_names = f.readlines()
last_names = [ln.strip() for ln in last_names]
last_names_dex = -1

ground_rise_y  = 2
ground_y       = wh - ground_rise_y
above_ground_y = ground_y - 1

BASEHQ_H = 100
BASEHQ_X = 600
BASEHQ_Y = above_ground_y - BASEHQ_H

things = []
things.append(  Gigan(1150, above_ground_y, 200, 600)) # huge mysterious alien 'statue'

basehq =        Building(         'BaseHQ',     BASEHQ_X, BASEHQ_Y,     400, BASEHQ_H)
things.append(basehq)

#things.append( Billboard(0, above_ground_y-200, w=300, h=200, text='Testing...'))

ganymede =      GanymedeClassShip('Ganymede',   colors['lightgray'], 160,      150)
ganymede.mov_dir = (0,1)
ganymede.landing_gear('moving','down')
for i in range(8):
    ganymede.add_passenger( Marine(0,0))
ganymede.disembark_passengers = True # will deploy Marines onto ground at colony after landing
things.append(ganymede)

hegland =       GanymedeClassShip('Hegland II', colors['lightgray'], BASEHQ_X+100, BASEHQ_Y-50, 210)
hegland.lg_posy = hegland.LGPOSY_RANGE[1]
hegland.set_y(BASEHQ_Y - hegland.height())
things.append(hegland)

def make_AlienShip():
    alien_ship = GeometryShip('Vyit', 500, 400, pts=[(0,1),(3,0),(4,0),(5,1)], scale=80.0, color=colors['darkgreen'])
    for i in range(7):
        alien_ship.add_passenger( AlienAdult(0,0))
    alien_ship.disembark_passengers = True # will deploy Aliens onto ground at colony after landing
    things.append(alien_ship)
#make_AlienShip()

def make_Neyn(x, y, c='darkmagenta', scale=15.0):
    ship = GeometryShip('Neyn', x, y, pts=[(0,1),(3,0),(4,0),(5,1)], scale=scale, color=colors[c])
    things.append(ship)
    return ship

def make_Ryvan(x, y, c='darkmagenta', scale=40.0):
    ship = GeometryShip('Ryvan', x, y, pts=[(0,2),(5,1),(7,1),(9,0),(8,2),(8,3),(6,2)], scale=scale, color=colors[c])
    things.append(ship)
    return ship

def make_Orvo(x, y, c='darkmagenta', scale=50.0):
    ship = GeometryShip('Orvo', x, y, pts=[(2,0),(8,0),(9,1),(10,5),(10,10),(9,10),(9,11),(6,11),(6,10),(4,10),(4,11),(1,11),(1,10),(0,10),(0,5),(1,1)], scale=scale, color=colors[c])
    things.append(ship)
    return ship

ALIENS_START_QTY = 3
for i in range(ALIENS_START_QTY):
    x = random.randrange(0,ww)
    y = above_ground_y
    o = AlienAdult(x,y)
    things.append(o)

ALIEN_EGGS_QTY = 12
for i in range(ALIEN_EGGS_QTY):
    hatch_ticks = random.randrange(180,250)
    x = 300 + random.randrange(0,20)
    egg = AlienEgg(x, above_ground_y, hatch_ticks=hatch_ticks)
    things.append(egg)

MARINES_START_QTY = 0 # 6
for i in range(MARINES_START_QTY):
    x = random.randrange(0,ww)
    y = above_ground_y
    things.append( Marine(x,y) )

CIVS = 5
for i in range(CIVS):
    new_civ_on_ground()

orvo = make_Orvo(50,0)
orvo.set_y(above_ground_y - orvo.height())
orvo.npc = True # needed to make ship cease once flies off-screen
orvo.mov_dir = (0,-1)

# landing field warning lights (they flash if ship expected to land or launch)
lf_x = 50; lf_w = 500
lf = LandingField('Aviron LF', lf_x, above_ground_y, lf_w, 5)
things.append(lf)
for x in range(lf_x, lf_x+lf_w+1, 50):
    lp = LightPost(x, above_ground_y, colors['yellow'], 10, 1, 5)
    lf.lightposts.append(lp)
    things.append(lp)

# base alarm light (flashes if emergency, like if alien invasion)
things.append( LightPost(BASEHQ_X+20,BASEHQ_Y))

x = random.randrange(0,ww)
y = above_ground_y
avatar = Avatar(x, y) # the user's avatar or PC (player character)
things.append(avatar)
focused = avatar

intro = "You live in a different universe. The universe of Aviron 7. You are on a mission. A secret mission known only to you. You have a laser pistol and an itch to scratch. The galaxy is your oyster. You don't even know what an oyster is. It might be like a Veraxian tigercat. You saw one of those once. On a holo-TV show. You like watching holo-TV. Oh look, a Marine assault shuttle is landing. Perhaps they've come because of the aliens that are killing all the colonists. Perhaps it's because of these aliens that the giant Orvo cargo freighter is taking off and fleeing the planet post-haste. Perhaps you should flee as well. Though you'd love to stay and see the fight. Marines like to kick ass and take names. And these evil alien bastards probably don't have names. So they'll just be kicking ass."
things.append( StoryOverlay(500, 130, intro, tock_life=200))

clock = None
game = MyGame()
mainstate = MyState(game)

music_list = []#'audio/Drawing_Restraint_9_05_-_Hunter_Vessel.mp3',] # only music in repo, rest are gitignored local
for i in os.walk('audio/music/'):
    dirpath, dirnames, filenames = i
    for dn in dirnames:
        dpath = os.path.join(dirpath, dn)
        fnames = os.listdir(dpath)
        for fn in fnames:
            fpath = os.path.join(dpath, fn)
            #print fpath
            music_list.append(fpath)
music_index = -1#random.randrange(-1, len(music_list)-1)
music_playing_fpath = None

msgs = []
MAX_MSGS = 100
news('They said in space noone can hear you scream...')

debug = False
paused = True
music_enabled = False #TODO True causes app to freeze a few secs after init
show_interiors = False

#print pygame.font.get_fonts()


if __name__ == '__main__':
    main()
