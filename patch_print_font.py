# encoding: utf-8
##############################################################################
#
#     patch for print font
#     Copyright (C) 2014  zkjiao@gmail.com
# 
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU Affero General Public License as
#     published by the Free Software Foundation, either version 3 of the
#     License, or (at your option) any later version.
# 
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU Affero General Public License for more details.
# 
#     You should have received a copy of the GNU Affero General Public License
#     along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from openerp.models import TransientModel, AbstractModel
from openerp.osv import fields
from openerp.api import Environment as Env
from openerp.report.render.rml2pdf import customfonts
from openerp.tools.safe_eval import safe_eval
from reportlab import rl_config
from reportlab.lib.styles import ParagraphStyle
from openerp.addons.base.res import res_font
import simplejson as json
import glob
import os

def _get_alt_sysconfig(env):
    config_obj = env["ir.config_parameter"].sudo()
    wrap_style = safe_eval(config_obj.get_param('wrap_style', 'False'))
    font_altns = json.loads(config_obj.get_param('font_altns', '{}'))
    return wrap_style, font_altns

def _set_alt_sysconfig(env, wrap_style, font_altns):
    config_obj = env["ir.config_parameter"].sudo()
    new_mappings = json.dumps(font_altns)
    config_obj.set_param('wrap_style', repr(wrap_style))
    config_obj.set_param('font_altns', new_mappings)
    return

_donot_sync = False
def _reload_sys_fonts(env):
    _donot_sync = True
    try:
        env['res.font']._scan_disk()
    finally:
        _donot_sync = False
    return

def list_all_sysfonts():
    """
        This function returns list of font directories of system.
    """
    filepath = []

    # Perform the search for font files ourselves, as reportlab's
    # TTFOpenFile is not very good at it.
    searchpath = list(set(customfonts.TTFSearchPath + rl_config.TTFSearchPath))
    for dirname in searchpath:
        for filename in glob.glob(os.path.join(os.path.expanduser(dirname), '*.[Tt][Tt][FfCc]')):
            filepath.append(filename)
    return filepath

class patch_print_font(AbstractModel):
    _inherit = 'res.font' 
    #Do not touch _name it must be same as _inherit
    #_name = 'res.font'
    def _scan_disk(self, cr, uid, context=None):
        res = True
        old_list_func = customfonts.list_all_sysfonts
        customfonts.list_all_sysfonts = list_all_sysfonts
        try:
            res = super(patch_print_font, self)._scan_disk(cr, uid, context=context)
        finally:
            customfonts.list_all_sysfonts = old_list_func
        return res
    
    def _sync(self, cr, uid, context=None):
        res = True
        if not _donot_sync:
            res = super(patch_print_font, self)._sync(cr, uid, context=context)
            env = Env(cr, uid, context)
            wrap_style, font_altns = _get_alt_sysconfig(env)
            if wrap_style:
                ParagraphStyle.defaults['wordWrap'] = 'CJK'
            for fontface, fontmode, fontname in font_altns:
                font_obj = env['res.font'].search(['&', ('path', '!=', '/dev/null'),
                    ('name', '=', fontname)])
                if not font_obj:
                    continue
                font_obj = font_obj[0]
                def _check(e):
                    family, name, filename, mode = e
                    return fontface != family or (fontmode != 'all' and fontmode != mode)
                customfonts.CustomTTFonts = filter(_check, customfonts.CustomTTFonts)
                customfonts.CustomTTFonts.append((fontface, font_obj.name, font_obj.path, fontmode))
        return res
    
class fontname_alternative(TransientModel):
    _name = 'fontface.alternative'

    def _fontname_list_get(self, cr, uid, context=None):
        env = Env(cr, uid, context)
        fonts = env['res.font'].search([('path', '!=', '/dev/null')])
        if len(fonts) == 0:
            _reload_sys_fonts(env)
            fonts = env['res.font'].search([('path', '!=', '/dev/null')])
        return [(font.name, font.name + '/' + font.family) for font in fonts]

    _columns = {
        'fontface': fields.char('Font Face', required=True),
        'fontmode': fields.selection([
            ('all','All'),
            ('normal','Normal'),
            ('bold','Bold'),
            ('italic','Italic/Oblique'),
            ('bolditalic', 'BoldItalic/BoldOblique')], 'Font Mode', required=True),
        'fontname': fields.selection(_fontname_list_get, 'Font Name', required=True)
    }
    
    _sql_constraints = [
        ('fontface_alternative_uniq', 'unique (fontface, fontmode)', \
            'You can not register two fonts with the same face and mode!'),    
    ]    

class font_alternative_settings(TransientModel):
    _name = 'fontface.alternative.settings'
    _inherit = 'res.config.settings'
    _columns = {
#         'group_font_alternative': fields.boolean("Group", group='base.group_user', \
#             implied_group='base.group_erp_manager'),
        'wrap_style': fields.boolean('CJK wrap', 
                    help=("If you are using CJK fonts,"
                        "check this option will wrap your "
                        "words properly at the edge of the  pdf report")),
        'font_altns': fields.many2many('fontface.alternative', 'fontface_alternative_settings_rel', \
                'settings_id', 'fontalt_id', "Font Alternative")
                
    }
    
    def _retrieve_link_altn_id(self, env, fontface, fontmode, fontname):
        tbl_font_alt = env["fontface.alternative"]
        altn = tbl_font_alt.search(['&', ('fontface', '=', fontface), \
                ('fontmode', '=', fontmode)])
        if len(altn) > 0:
            altn = altn[0]
            altn.write({'fontname': fontname})
        else:
            altn = tbl_font_alt.create(
                {'fontface': fontface, 'fontmode':fontmode, 
                 'fontname': fontname})
        return altn.id;

    def _get_font_altns(self, env, font_altns):
        tbl_font_alt = env["fontface.alternative"]
        temp_altns = []
        for fontface, fontmode, fontname in font_altns:
            if not env['res.font'].search(['&', ('path', '!=', '/dev/null'),
                ('name', '=', fontname)]):
                continue
            altn_id = self._retrieve_link_altn_id(env, fontface, fontmode, fontname)

            temp_altns.append(altn_id)
        return temp_altns

    def _get_defaut_altns(self, env):
        chinese_fonts = ['SimHei', 'SimSun', 'WenQuanYiZenHei', 'WenQuanYiMicroHei']
        report_facemodes = [('Helvetica', 'all'),
                ('DejaVuSans', 'all'),
                ('Times', 'all'),
                ('Times-Roman', 'all'),
                ('Courier', 'all')]
        link_altn_ids = []
        for font_name in chinese_fonts:
            if env['res.font'].search(['&', ('path', '!=', '/dev/null'),
                ('name', '=', font_name)]):
                for font_face, font_mode in report_facemodes:
                    altn_id = self._retrieve_link_altn_id(env, font_face, \
                        font_mode, font_name)
                    link_altn_ids.append(altn_id)
                return link_altn_ids
            pass
        return link_altn_ids

    def get_default_font_altns(self, cr, uid, fields, context):
        env = Env(cr, uid, context)
        wrap_style, font_altns = _get_alt_sysconfig(env)
        if not font_altns:
            font_altns = self._get_defaut_altns(env)
        else:
            font_altns = self._get_font_altns(env, font_altns)
            if not font_altns:
                font_altns = self._get_defaut_altns(env)
        return {"wrap_style": wrap_style, 
            'font_altns': font_altns}

    def set_font_altns(self, cr, uid, ids, context):
        obj = self.browse(cr, uid, ids[0], context)
        _set_alt_sysconfig(obj.env, obj.wrap_style, 
            [(alt.fontface, alt.fontmode,alt.fontname) for alt in obj.font_altns])
        obj.env['res.font']._sync()
        pass
    
    def act_reload_sys_fonts(self, cr, uid, ids, context=None):
        _reload_sys_fonts(Env(cr, uid, context))
        pass
