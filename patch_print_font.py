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
from reportlab import rl_config
from reportlab.lib.styles import ParagraphStyle
from openerp.addons.base.res import res_font
import glob
import os

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
        old_list_func = customfonts.list_all_sysfonts
        customfonts.list_all_sysfonts = list_all_sysfonts
        res = super(patch_print_font, self)._scan_disk(cr, uid, context=context)
        customfonts.list_all_sysfonts = old_list_func
        return res
    
    def _sync(self, cr, uid, context=None):
        res = super(patch_print_font, self)._sync(cr, uid, context=context)
        return res
    
class fontname_define(TransientModel):
    _name = 'fontname.define'
    _rec_name = 'fontname' 
    
    _columns = {
        'fontname': fields.char('Font Name', size=64, required=False, readonly=False),
    }
    _sql_constraints = [
        ('fontname_define_uniq', 'unique (fontname)', 'The Name of the font must be unique !')
    ]

class fontname_alternative(TransientModel):
    _name = 'fontname.alternative'
    
    _columns = {
        'fontname': fields.many2one('fontname.define', 'Font Name', required=True, \
            ondelete = 'cascade'),
        'fontmode': fields.selection([
            ('all','All'),
            ('normal','Normal'),
            ('bold','Bold'),
            ('italic','Italic/Oblique'),
            ('bolditalic', 'BoldItalic/BoldOblique')], 'Font Mode', required=True),
        'fontnamealts': fields.many2many('fontname.define', 'fontname_alternative_rel', \
            'alt_id', 'name_id', 'Font Alternatives')
    }
    
    _sql_constraints = [
        ('fontname_alternative_uniq', 'unique (fontname, fontmode)', \
            'You can not register two fonts with the same name and mode!'),    
    ]
    
    def onchange_fontname(self, cr, uid, ids, font_id):
        return {'domain': {'fontnamealts': [('id', '!=', font_id)]}}

class font_alternatives_wizard(TransientModel):
    _name = 'fontname.alternatives.settings'
    _inherit = 'res.config.settings'
    _columns = {
        'group_font_alternatives': fields.boolean("Group", group='base.group_user', \
            implied_group='base.group_erp_manager'),
        'wrap': fields.boolean('CJK wrap', 
            help="If you are using CJK fonts, \
                check this option will wrap your \
                words properly at the edge of the  pdf report"),
        'fontnamealts_map': fields.many2many('fontname.alternative', 'fontname_alternatives_wizard_rel', \
                'wizard_id', 'fontalt_id', "Font Alternatives")
                
    }
    
    def get_default_wrap(self, cr, uid, fields, context):
        if 'wrap' not in fields:
            return {}
        return {"wrap": ParagraphStyle.defaults['wordWrap'] == 'CJK'}

    def _get_fontname_id(self, env, fontname):
        tbl_font_def = env["fontname.define"]
        fontname_rec = tbl_font_def.search([('fontname', '=', fontname)])
        if len(fontname_rec) > 0:
            fontname_rec = fontname_rec[0]
        else:
            fontname_rec = tbl_font_def.create({'fontname': fontname})
        return fontname_rec.id
    
    def _get_fontnamealts_map(self, env):
        tbl_font_alt = env["fontname.alternative"]
        fontnamealts_map = []
        for builtin_alt in res_font.BUILTIN_ALTERNATIVES:
            fontname = builtin_alt[0];
            fontmode = builtin_alt[1];
            altnames = builtin_alt[2];
            fontname_id = self._get_fontname_id(env, fontname)
            fontnamealts = [];
            for altname in altnames:
                alt_id = self._get_fontname_id(env, altname)
                fontnamealts.append(alt_id)
            fontnamealt_rec = tbl_font_alt.search(['&', ('fontname', '=', fontname_id), \
                ('fontmode', '=', fontmode)])
            if len(fontnamealt_rec) > 0:
                fontnamealt_rec = fontnamealt_rec[0]
                fontnamealt_rec.write({'fontnamealts': [(6,0,fontnamealts)]})
            else:
                fontnamealt_rec = tbl_font_alt.create(
                    {'fontname': fontname_id, 'fontmode':fontmode, 
                     'fontnamealts': [(6,0,fontnamealts)]})

            fontnamealts_map.append(fontnamealt_rec.id)
        return fontnamealts_map
    
    def act_reload_fonts(self, cr, uid, ids, context=None):
        return self.pool.get("res.font")._scan_disk(cr, uid, context=context)
    
    def act_set_chinesefont(self, cr, uid, ids, context=None):
        obj = self.browse(cr, uid, ids[0], context)
        chinese_fonts = ['SimHei', 'SimSun', 'WenQuanYiZenHei']
        builtin_alternatives = []
        for builtin_alt in res_font.BUILTIN_ALTERNATIVES:
            new_alts = chinese_fonts #+ [name for name in builtin_alt[2] if name not in chinese_fonts]
            builtin_alternatives.append((
                builtin_alt[0], builtin_alt[1], new_alts))
        
        res_font.BUILTIN_ALTERNATIVES = builtin_alternatives
        obj.write({'fontnamealts_map': self._get_fontnamealts_map(obj.env)})
        pass

    def get_default_font_alts(self, cr, uid, fields, context):
        if 'fontnamealts_map' not in fields:
            return {}
        env = Env(cr, uid, context)
        
        tbl_res_font = env["res.font"]
        for font in tbl_res_font.search([]):
            self._get_fontname_id(env, font.name)

        return {'fontnamealts_map': self._get_fontnamealts_map(env)}

    def set_wrap(self, cr, uid, ids, context):
        obj = self.browse(cr, uid, ids[0], context)
        if obj.wrap:
            ParagraphStyle.defaults['wordWrap'] = 'CJK'
        pass

    def set_font_alts(self, cr, uid, ids, context):
        obj = self.browse(cr, uid, ids[0], context)
        builtin_alternatives = []
        for builtin_alt in obj.fontnamealts_map:
            alts = []
            for alt in builtin_alt.fontnamealts:
                alts.append(alt.fontname)
            builtin_alternatives.append((
                builtin_alt.fontname.fontname, builtin_alt.fontmode, alts))
        
        res_font.BUILTIN_ALTERNATIVES = builtin_alternatives
        env = Env(cr, uid, context)
        tbl_res_font = env["res.font"]
        tbl_res_font._sync()
