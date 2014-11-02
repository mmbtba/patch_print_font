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
from openerp.report.render.rml2pdf import trml2pdf
from openerp.report.render.rml2pdf import customfonts
from openerp.tools.safe_eval import safe_eval
from reportlab import rl_config
from reportlab.lib.styles import ParagraphStyle
from openerp.addons.base.res import res_font
import simplejson as json
import glob
import os

import logging
_logger = logging.getLogger(__name__)

encoding = 'utf-8'

def _get_alt_sysconfig(env):
    config_obj = env["ir.config_parameter"].sudo()
    wrap_style = safe_eval(config_obj.get_param('reportlab.wrap_style', 'False'))
    default_font = config_obj.get_param('reportlab.default_font', '')
    font_altns = json.loads(config_obj.get_param('reportlab.font_altns', '{}'))
    return wrap_style, default_font, font_altns

def _set_alt_sysconfig(env, wrap_style, default_font, font_altns):
    config_obj = env["ir.config_parameter"].sudo()
    font_altns = json.dumps(font_altns)
    config_obj.set_param('reportlab.wrap_style', repr(wrap_style))
    config_obj.set_param('reportlab.default_font', default_font)
    config_obj.set_param('reportlab.font_altns', font_altns)
    return

# hook trml2pdf.select_fontname
_old_select_fontname = trml2pdf.select_fontname
def uninstall_hook(cr, registry):
    trml2pdf.select_fontname = _old_select_fontname
    _logger.info("GoodBye!!")
    
def hook_select_fontname(f, default_font, dict_font_altns):
    _old_func = f
    _default_font = default_font
    _dict_font_altns = dict_font_altns
    def select_fontname(fontname, default_fontname):
        font, default = fontname, default_fontname
        ret = _dict_font_altns.get(fontname, '') or _default_font
        if not ret:
            ret =  _old_func(fontname, default_fontname)
        _logger.info('select_fontname: font(%s), default(%s), return(%s)',
            font, default, ret)
        return ret
    return select_fontname

_donot_sync = False
def _reload_sys_fonts(env):
    _donot_sync = True
    try:
        env['res.font']._scan_disk()
    finally:
        _donot_sync = False
    return
# search res_font by fontname
def _search_font(env, fontname=None):
    if fontname is None:
        return env['res.font'].search([('path', '!=', '/dev/null')])
    else:
        return env['res.font'].search(['&', ('path', '!=', '/dev/null'),
                    ('name', '=', fontname)])

def _list_fonts(env):
    fonts = _search_font(env)
    if len(fonts) == 0:
        _reload_sys_fonts(env)
        fonts = _search_font(env)
    return [(font.name, font.name + '/' + font.family) for font in fonts]

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
            # this code will be launched at least once
            env = Env(cr, uid, context)
            wrap_style, default_font, font_altns = _get_alt_sysconfig(env)
            if wrap_style:
                ParagraphStyle.defaults['wordWrap'] = 'CJK'
            
            if (not default_font) and (not _search_font(env, default_font)):
                default_font = ''
             
            _dict_font_altns = {}
            for fontface, fontname in font_altns:
                font_obj = _search_font(env, fontname)
                if font_obj:
                    _dict_font_altns[fontface] = fontname
                    font_obj = font_obj[0]
                    def _check(e):
                        family, name, filename, mode = e
                        return fontface != family and fontface != name
                    customfonts.CustomTTFonts = filter(_check, customfonts.CustomTTFonts)
                    customfonts.CustomTTFonts.append((fontface, fontname, font_obj.path, 'all'))
            
            trml2pdf.select_fontname = \
                hook_select_fontname(_old_select_fontname, default_font, _dict_font_altns)
        return res
    
class fontname_alternative(TransientModel):
    _name = 'fontface.alternative'

    def _fontname_list_get(self, cr, uid, context=None):
        env = Env(cr, uid, context)
        return _list_fonts(env)

    _columns = {
        'fontface': fields.char('Font Face', required=True),
        'fontname': fields.selection(_fontname_list_get, 'Font Name', required=True)
    }
    
    _sql_constraints = [
        ('fontface_alternative_uniq', 'unique (fontface)', \
            'You can not register two fonts with the same face!'),    
    ]    

_chinese_fonts = (
    'SimHei', 'SimSun', 'WenQuanYiZenHei', 'WenQuanYiMicroHei')
_report_faces = (
    'Courier', 'Courier-Bold', 'Courier-Oblique', 'Courier-BoldOblique',
    'DejaVuSans', 'DejaVuSans-Bold', 'DejaVuSans-Oblique', 'DejaVuSans-BoldOblique',
    'Helvetica', 'Helvetica-Bold', 'Helvetica-Oblique', 'Helvetica-BoldOblique',
    'Times', 'Times-Roman', 'Times-Bold', 'Times-Italic', 'Times-BoldItalic')
class font_alternative_settings(TransientModel):
    _name = 'fontface.alternative.settings'
    _inherit = 'res.config.settings'
    
    def _fontname_list_get(self, cr, uid, context=None):
        env = Env(cr, uid, context)
        return _list_fonts(env)

    _columns = {
#         'group_font_alternative': fields.boolean("Group", group='base.group_user', \
#             implied_group='base.group_erp_manager'),
        'wrap_style': fields.boolean('CJK wrap', 
                    help=("If you are using CJK fonts,"
                        "check this option will wrap your "
                        "words properly at the edge of the  pdf report")),
        'default_font': fields.selection(_fontname_list_get, 'Default Font Name',
                    help=("Default alternative For Unknown PDF Font.")),
        'font_altns': fields.many2many('fontface.alternative', 'fontface_alternative_settings_rel', \
                'settings_id', 'fontalt_id', "Font Alternative")
                
    }

    def _retrieve_link_altn_id(self, env, fontface, fontname):
        tbl_font_alt = env["fontface.alternative"]
        altn = tbl_font_alt.search([('fontface', '=', fontface)])
        if len(altn) > 0:
            altn = altn[0]
            altn.write({'fontname': fontname})
        else:
            altn = tbl_font_alt.create(
                {'fontface': fontface, 'fontname': fontname})
        return altn.id;

    def _get_font_altns(self, env, font_altns):
        tbl_font_alt = env["fontface.alternative"]
        temp_altns = []
        for fontface, fontname in font_altns:
            if not _search_font(env, fontname):
                continue
            altn_id = self._retrieve_link_altn_id(env, fontface, fontname)

            temp_altns.append(altn_id)
        return temp_altns

    def _get_defaut_altns(self, env):
        link_altn_ids = []
        for font_name in _chinese_fonts:
            if _search_font(env, font_name):
                for font_face in _report_faces:
                    altn_id = self._retrieve_link_altn_id(env, font_face, font_name)
                    link_altn_ids.append(altn_id)
                return link_altn_ids
            pass
        return link_altn_ids

    def get_default_font_altns(self, cr, uid, fields, context):
        env = Env(cr, uid, context)
        wrap_style, default_font, font_altns = _get_alt_sysconfig(env)
        if not default_font and not _search_font(env, default_font):
            for font_name in _chinese_fonts:
                if _search_font(env, font_name):
                    default_font = font_name
                    break
        if not font_altns:
            font_altns = self._get_defaut_altns(env)
        else:
            font_altns = self._get_font_altns(env, font_altns)
            if not font_altns:
                font_altns = self._get_defaut_altns(env)
        return {"wrap_style": wrap_style, 'default_font': default_font,
            'font_altns': font_altns}

    def set_font_altns(self, cr, uid, ids, context):
        obj = self.browse(cr, uid, ids[0], context)
        _set_alt_sysconfig(obj.env, obj.wrap_style, obj.default_font,
            [(alt.fontface, alt.fontname) for alt in obj.font_altns])
        obj.env['res.font']._sync()
        pass
    
    def act_reload_sys_fonts(self, cr, uid, ids, context=None):
        _reload_sys_fonts(Env(cr, uid, context))
        pass
