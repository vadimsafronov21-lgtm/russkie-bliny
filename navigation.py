"""Two-level seller workspace; navigation never recreates drafts or chart widgets."""
from datetime import date
import platform
import re
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QCheckBox,QStackedWidget
from ui_theme import ASSETS,BURGUNDY,svg_icon
from ui_motion import MotionButton,reveal_heading


class WorkspaceNavigation:
    ROUTES={
        'stock':[('today','Дела на сегодня','check'),('inventory','Обзор запасов','stock'),('order','Заявка','order'),('history','История заявок','history'),('imports','Данные остатков','import')],
        'demand':[('dynamics','Продажи и прогноз','chart'),('months','Сравнение месяцев','chart'),('availability','Наличие блюд','check'),('pilot','Отчёт пилота','history'),('imports','Данные продаж','import')],
    }

    def build_workspace(self):
        self.active_domain='stock'; self.active_view='inventory'; self.last_views={'stock':'inventory','demand':'dynamics'}; self.navigation_ready=False; self._routing=False
        root=QWidget(); self.setCentralWidget(root); outer=QVBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        header=QFrame(); header.setObjectName('workspaceHeader'); top=QHBoxLayout(header); self.header_layout=top; top.setContentsMargins(25,15,26,15); top.setSpacing(16)
        identity=QVBoxLayout(); identity.setSpacing(6)
        brand=QLabel(); brand.setPixmap(QPixmap(str(ASSETS/'krona-wordmark.png')).scaledToWidth(150,Qt.TransformationMode.SmoothTransformation)); identity.addWidget(brand)
        client=QLabel('РУССКИЕ БЛИНЫ'); client.setObjectName('workspace'); identity.addWidget(client); top.addLayout(identity)
        domains=QFrame(); domains.setObjectName('viewSwitch'); domains.setFixedHeight(46); domain_layout=QHBoxLayout(domains); domain_layout.setContentsMargins(4,4,4,4); domain_layout.setSpacing(3); self.domain_buttons={}
        for domain,title,icon in [('stock','Остатки','stock'),('demand','Спрос','chart')]:
            b=MotionButton(title,'domain'); b.setObjectName('viewMode'); b.set_nav_icon(icon); b.setIconSize(QSize(18,18)); b.setMinimumWidth(115); b.clicked.connect(lambda checked=False,d=domain:self.switch_domain(d)); self.domain_buttons[domain]=b; domain_layout.addWidget(b)
        top.addWidget(domains); top.addStretch()
        self.operator_profile=QFrame(); self.operator_profile.setObjectName('operatorProfile'); self.operator_profile.setFixedHeight(48)
        profile=QHBoxLayout(self.operator_profile); profile.setContentsMargins(0,0,0,0); profile.setSpacing(12)
        divider=QFrame(); divider.setObjectName('profileDivider'); divider.setFixedSize(1,34); profile.addWidget(divider); profile.addSpacing(7)
        self.operator_avatar=QLabel(); self.operator_avatar.setObjectName('operatorAvatar'); self.operator_avatar.setFixedSize(34,34); self.operator_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter); profile.addWidget(self.operator_avatar)
        profile_text=QVBoxLayout(); profile_text.setSpacing(4); profile_text.setContentsMargins(0,0,0,0)
        self.operator_name=QLabel(); self.operator_name.setObjectName('operatorName'); self.operator_name.setMaximumWidth(245); profile_text.addWidget(self.operator_name)
        self.point_name=QLabel(); self.point_name.setObjectName('operatorContext'); self.point_name.setMaximumWidth(245); profile_text.addWidget(self.point_name); profile.addLayout(profile_text)
        self.point=QComboBox(); self.point.setMinimumWidth(245)
        for p in self.store.get('tables',{}).get('points',[]): self.point.addItem(p['name'],str(p['id']))
        configured=self.point.findData(str(self.store.get('settings',{}).get('terminal_point','')))
        if configured>=0: self.point.setCurrentIndex(configured)
        self.point.currentIndexChanged.connect(self.point_changed)
        self.banner=QLabel(); self.banner.setObjectName('demo'); self.banner.setFixedHeight(34); top.addWidget(self.banner)
        self.day_label=QLabel(date.today().strftime('%d.%m.%Y')); self.day_label.setObjectName('subtitle'); top.addWidget(self.day_label); top.addWidget(self.operator_profile); outer.addWidget(header)
        body=QHBoxLayout(); body.setContentsMargins(0,0,0,0); body.setSpacing(0); outer.addLayout(body,1)
        sidebar=QWidget(); self.sidebar=sidebar; sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(198); side=QVBoxLayout(sidebar); side.setContentsMargins(14,25,14,18); side.setSpacing(7)
        caption=QLabel('РАЗДЕЛ'); caption.setObjectName('eyebrow'); caption.setContentsMargins(12,0,0,0); side.addWidget(caption)
        self.side_title=QLabel(); self.side_title.setObjectName('section'); self.side_title.setContentsMargins(12,5,0,16); side.addWidget(self.side_title)
        links=QWidget(); self.side_links=QVBoxLayout(links); self.side_links.setContentsMargins(0,0,0,0); self.side_links.setSpacing(6); side.addWidget(links); side.addStretch()
        settings=MotionButton('Настройки точки'); settings.setObjectName('workspaceSettings'); settings.set_nav_icon('settings'); settings.clicked.connect(lambda:self.select_route(self.active_domain,'settings')); self.settings_nav=settings; side.addWidget(settings)
        local=QFrame(); local.setObjectName('rail'); localbox=QVBoxLayout(local); localbox.setContentsMargins(12,13,12,13); localbox.setSpacing(8)
        self.local_status=QLabel('Данные на этом компьютере'); self.local_status.setObjectName('subtitle'); self.local_status.setWordWrap(True); localbox.addWidget(self.local_status)
        self.offline=QCheckBox('Без связи'); self.offline.toggled.connect(self.network_changed); localbox.addWidget(self.offline); side.addWidget(local)
        body.addWidget(sidebar)
        content=QWidget(); area=QVBoxLayout(content); area.setContentsMargins(26,17,26,14); area.setSpacing(13)
        self.breadcrumb=QLabel(); self.breadcrumb.setObjectName('workspacePath'); area.addWidget(self.breadcrumb)
        self.problem_box=QFrame(); self.problem_box.setObjectName('rail'); problem_layout=QHBoxLayout(self.problem_box)
        self.problem_text=QLabel(); self.problem_text.setObjectName('notice'); self.problem_text.setWordWrap(True); problem_layout.addWidget(self.problem_text,1)
        self.problem_action=QPushButton('Проверить данные'); self.problem_action.clicked.connect(self.resolve_problem); problem_layout.addWidget(self.problem_action); area.addWidget(self.problem_box); self.problem_box.hide()
        self.stack=QStackedWidget(); area.addWidget(self.stack,1)
        self.status=QLabel(content); self.status.setObjectName('workspaceStatus'); self.status.hide(); body.addWidget(content,1)
        self.side_buttons={}; self._side_domain=None; self.page_titles=[]; self.page_subtitles=[]

    def update_identity(self):
        name=self.author().strip() or 'Продавец'; parts=[p for p in re.split(r'[\s-]+',name) if p]
        initials=''.join(p[0] for p in parts[:2]).upper()
        self.operator_avatar.setText(initials); self.operator_avatar.setAccessibleName('Инициалы: '+name)
        self.operator_name.ensurePolished(); self.point_name.ensurePolished()
        self.operator_name.setText(self.operator_name.fontMetrics().elidedText(name,Qt.TextElideMode.ElideRight,245))
        self.operator_name.setToolTip(name+'\nИмя для журнала. Авторизация терминала пока не подключена.')
        terminal=self.store.get('settings',{}).get('terminal_name','').strip() or platform.node()
        context=(self.point.currentText() or 'Точка не настроена')+(' · '+terminal if terminal else '')
        self.point_name.setText(self.point_name.fontMetrics().elidedText(context,Qt.TextElideMode.ElideRight,245)); self.point_name.setToolTip(context)

    def sync_navigation(self):
        title='Остатки' if self.active_domain=='stock' else 'Спрос'; self.side_title.setText(title)
        for domain,b in self.domain_buttons.items():
            b.setChecked(domain==self.active_domain)
        if self._side_domain!=self.active_domain:
            while self.side_links.count():
                item=self.side_links.takeAt(0)
                if item.widget(): item.widget().hide(); item.widget().deleteLater()
            self.side_buttons={}; self._side_domain=self.active_domain
            for view,name,icon in self.ROUTES[self.active_domain]:
                b=MotionButton(name); b.set_nav_icon(icon); b.setIconSize(QSize(18,18))
                b.clicked.connect(lambda checked=False,v=view,d=self.active_domain:self.select_route(d,v)); self.side_links.addWidget(b); self.side_buttons[view]=b
        for view,b in self.side_buttons.items(): b.setChecked(view==self.active_view)
        name=next((name for view,name,_ in self.ROUTES[self.active_domain] if view==self.active_view),'Настройки точки')
        self.breadcrumb.setText(title+' / '+name); self.settings_nav.setChecked(self.active_view=='settings')
        self.update_identity()

    def switch_domain(self,domain): self.select_route(domain,self.last_views[domain])

    def select_route(self,domain,view):
        if view not in {r[0] for r in self.ROUTES[domain]}|{'settings'}: raise ValueError('Неизвестный подраздел')
        changed=(domain,view)!=(self.active_domain,self.active_view)
        if (domain,view)!=(self.active_domain,self.active_view) and hasattr(self,'notifications'):
            self.notifications.dismiss_success()
        self.active_domain=domain; self.active_view=view; self.last_views[domain]=view; self._routing=True
        try:
            index={'inventory':0,'dynamics':0,'months':0,'order':1,'imports':2,'history':3,'settings':4,'today':5,'availability':6,'pilot':7}[view]; self.stack.setCurrentIndex(index)
            if index==0:
                self.stock_views.setCurrentIndex(1 if view=='inventory' else 0)
                if view!='inventory': self.analytics.mode_combo.setCurrentIndex(1 if view=='months' else 0)
                if view=='months': self.analytics.chart_tabs.setCurrentIndex(0)
                self.page_titles[0].setText({'inventory':'Остатки и предупреждения','dynamics':'Продажи и прогноз','months':'Сравнение месяцев'}[view])
                self.page_subtitles[0].setText('Сначала сверьте фактические остатки. Затем сформируйте заявку на пополнение.' if view=='inventory' else 'Подтверждённые продажи и расчётный спрос · '+self.point.currentText())
            if view=='imports':
                self.page_titles[2].setText('Данные остатков' if domain=='stock' else 'Данные продаж'); self.refresh_quality()
            if view=='history': self.reload_history()
            if view=='today': self.refresh_operations()
            if view=='availability': self.refresh_availability()
            if view=='pilot': self.refresh_pilot()
            self.sync_navigation()
            if changed and self.navigation_ready: reveal_heading(self.page_titles[index])
            self.schedule_workspace_save()
        finally: self._routing=False

    def chart_mode_changed(self,index):
        if self.navigation_ready and not self._routing and self.active_domain=='demand' and self.active_view in ('dynamics','months'):
            self.active_view='months' if index==1 else 'dynamics'; self.last_views['demand']=self.active_view; self.sync_navigation()
            self.page_titles[0].setText('Сравнение месяцев' if index else 'Продажи и прогноз')

    def navigate(self,index):
        domain=self.active_domain if index in (2,4) else 'stock'
        self.select_route(domain,{0:'inventory',1:'order',2:'imports',3:'history',4:'settings'}[index])
