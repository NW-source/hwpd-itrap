import pandas as pd
import folium
from folium import plugins


DAY_COLORS = ['blue', 'red', 'green', 'orange', 'purple', 'pink', 'cadetblue', 'darkred']


def create_master_map(df_master, leader_plate="", follower_plate="", is_ghost_case=False, convoy_dates=None, **kwargs):
    """
    สร้าง Master Operational Map (Folium):
    - Ghost Plate (E1): Timeline A (Blue) vs Timeline B (Red Twin)
    - Convoy (E2): 🔴 พิกัดเส้นทางรถนำ vs 🔵 พิกัดเส้นทางรถตาม (วันเกิดเหตุไฮไลต์สีแดงเด่นชัด 🚨🔥)
    - Suspect (E3-E5): 📍 พิกัดจุดตรวจพบ และเส้นทางสัญจรปกติ (วันสัญจรยาวไฮไลต์สีแดง ⭐🔥)
    """
    if df_master.empty:
        m = folium.Map(location=[13.7563, 100.5018], zoom_start=6)
        return m

    center_lat = df_master['ละติจูด'].mean()
    center_lon = df_master['ลองจิจูด'].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=10)

    unique_plates = df_master['ทะเบียนรถ'].unique()

    is_convoy = bool(leader_plate and follower_plate)
    has_twin = is_ghost_case or (('is_twin' in df_master.columns) and df_master['is_twin'].any())

    fg_hz_rings   = folium.FeatureGroup(name="🚨 วงแหวนพื้นที่ควบคุมจุดสกัด (แดง-วิกฤต / เหลือง-เฝ้าระวัง)")
    fg_ho_main    = folium.FeatureGroup(name="🏠 พื้นที่กบดานถาวร/ฐานที่มั่น (วงแหวนม่วงเข้ม >12 ชม.)")
    fg_ho_sub     = folium.FeatureGroup(name="⏳ จุดหยุดพักสินค้าชั่วคราว (วงแหวนม่วงอ่อน 3-12 ชม.)")
    fg_cp_main    = folium.FeatureGroup(name="👮 จุดสกัดกั้นหลัก (⭐️ ดาวตำรวจ)")
    fg_cp_sub     = folium.FeatureGroup(name="👮 จุดสกัดกั้นรอง (🛡️ โล่ตำรวจ)")

    # 1. Markers according to case type
    if has_twin:
        fg_real_units = folium.FeatureGroup(name="🔵 พิกัดสัญจรปกติ (Timeline A)")
        fg_twin_units = folium.FeatureGroup(name="🔴 พิกัดรถสวมทะเบียน (Timeline B Ghost Paradox)")
        for row in df_master.itertuples():
            info_txt = (
                f"<b>ทะเบียน:</b> {row.ทะเบียนรถ}<br>"
                f"<b>กล้อง:</b> {row.จุดติดตั้งกล้อง}<br>"
                f"<b>เวลา:</b> {row.เวลา}<br>"
                f"<b>ความเร็ว:</b> {row.Speed_kmh:.0f} กม./ชม."
            )
            if getattr(row, 'is_twin', False):
                folium.CircleMarker(
                    location=[row.ละติจูด, row.ลองจิจูด],
                    radius=7, color='red', fill=True, fill_color='darkred',
                    popup=folium.Popup(info_txt, max_width=250)
                ).add_to(fg_twin_units)
            else:
                folium.CircleMarker(
                    location=[row.ละติจูด, row.ลองจิจูด],
                    radius=6, color='blue', fill=True, fill_color='dodgerblue',
                    popup=folium.Popup(info_txt, max_width=250)
                ).add_to(fg_real_units)
        fg_real_units.add_to(m)
        fg_twin_units.add_to(m)
    elif is_convoy:
        fg_ldr_units = folium.FeatureGroup(name=f"🔴 พิกัดจุดตรวจรถนำ ({leader_plate})")
        fg_flw_units = folium.FeatureGroup(name=f"🔵 พิกัดจุดตรวจรถตาม ({follower_plate})")
        for row in df_master.itertuples():
            info_txt = (
                f"<b>ทะเบียน:</b> {row.ทะเบียนรถ}<br>"
                f"<b>กล้อง:</b> {row.จุดติดตั้งกล้อง}<br>"
                f"<b>เวลา:</b> {row.เวลา}<br>"
                f"<b>ความเร็ว:</b> {row.Speed_kmh:.0f} กม./ชม."
            )
            if row.ทะเบียนรถ == leader_plate:
                folium.CircleMarker(
                    location=[row.ละติจูด, row.ลองจิจูด],
                    radius=7, color='red', fill=True, fill_color='darkred',
                    popup=folium.Popup(info_txt, max_width=250)
                ).add_to(fg_ldr_units)
            else:
                folium.CircleMarker(
                    location=[row.ละติจูด, row.ลองจิจูด],
                    radius=6, color='blue', fill=True, fill_color='dodgerblue',
                    popup=folium.Popup(info_txt, max_width=250)
                ).add_to(fg_flw_units)
        fg_ldr_units.add_to(m)
        fg_flw_units.add_to(m)
    else:
        fg_pts = folium.FeatureGroup(name="📍 พิกัดจุดตรวจพบ")
        for row in df_master.itertuples():
            info_txt = (
                f"<b>ทะเบียน:</b> {row.ทะเบียนรถ}<br>"
                f"<b>กล้อง:</b> {row.จุดติดตั้งกล้อง}<br>"
                f"<b>เวลา:</b> {row.เวลา}<br>"
                f"<b>ความเร็ว:</b> {row.Speed_kmh:.0f} กม./ชม."
            )
            folium.CircleMarker(
                location=[row.ละติจูด, row.ลองจิจูด],
                radius=6, color='blue', fill=True, fill_color='dodgerblue',
                popup=folium.Popup(info_txt, max_width=250)
            ).add_to(fg_pts)
        fg_pts.add_to(m)

    # 2. AntPath Trajectory per Vehicle with Leader/Follower Tagging & Highlights
    convoy_dates_set = set(convoy_dates) if convoy_dates else set()

    for idx, plate in enumerate(unique_plates):
        if is_convoy:
            if plate == leader_plate:
                role_tag = "🔴 พิกัดเส้นทางรถนำ"
                car_color = "red"
            elif plate == follower_plate:
                role_tag = "🔵 พิกัดเส้นทางรถตาม"
                car_color = "blue"
            else:
                role_tag = f"🚗 เส้นทาง: {plate}"
                car_color = DAY_COLORS[idx % len(DAY_COLORS)]
        else:
            role_tag = f"🚗 เส้นทาง: {plate}"
            car_color = DAY_COLORS[idx % len(DAY_COLORS)]

        car_data = df_master[df_master['ทะเบียนรถ'] == plate].sort_values('Datetime')

        date_info_list = []
        for date in car_data['วันที่'].unique():
            day_data = car_data[car_data['วันที่'] == date]
            n_cams = day_data['จุดติดตั้งกล้อง'].nunique()
            is_cv_day = is_convoy and (date in convoy_dates_set)
            is_long_day = (not is_convoy) and (n_cams >= 5)
            date_info_list.append({
                'date': date, 'day_data': day_data, 'n_cams': n_cams,
                'is_cv_day': is_cv_day, 'is_long_day': is_long_day
            })

        # เรียงวันสำคัญขึ้นบนสุด (วันเกิดเหตุขบวน หรือ วันผ่านกล้องยาว >= 5 จุด)
        date_info_list.sort(key=lambda x: (x['is_cv_day'], x['is_long_day'], x['n_cams']), reverse=True)

        # กรองแยกวันสำคัญ (วันขบวน / วันสัญจรยาว) vs วันปกติกล้องเดียว (1 กล้อง)
        important_days = [d for d in date_info_list if d['is_cv_day'] or d['is_long_day'] or d['n_cams'] >= 2]
        minor_days = [d for d in date_info_list if d not in important_days]

        # 1. สร้างเลเยอร์เดี่ยวของวันสำคัญแต่ละวัน
        for d_info in important_days:
            date = d_info['date']
            day_data = d_info['day_data']
            n_cams = d_info['n_cams']

            if is_convoy:
                if d_info['is_cv_day']:
                    layer_label = f"🚨🔥 {role_tag}: {plate} ({date} — {n_cams} จุด) [วันสัญจรขบวน]"
                else:
                    layer_label = f"{role_tag}: {plate} ({date} — {n_cams} จุด)"
            else:
                if d_info['is_long_day']:
                    layer_label = f"⭐🔥 🚗 เส้นทาง: {plate} ({date} — {n_cams} จุด) [วันสัญจรยาว]"
                else:
                    layer_label = f"🚗 เส้นทาง: {plate} ({date} — {n_cams} จุด)"

            fg_track = folium.FeatureGroup(name=layer_label)
            coords_list = []

            for i in range(len(day_data)):
                row = day_data.iloc[i]
                coords = (row['ละติจูด'], row['ลองจิจูด'])
                coords_list.append(coords)
                seq = i + 1
                info = (
                    f"<b>ลำดับ {seq}:</b> {plate} ({role_tag})<br>"
                    f"<b>กล้อง:</b> {row['จุดติดตั้งกล้อง']}<br>"
                    f"<b>เวลา:</b> {row['เวลา']}"
                )
                folium.Marker(
                    location=coords,
                    popup=folium.Popup(info, max_width=250),
                    icon=folium.Icon(color=car_color, icon='car', prefix='fa')
                ).add_to(fg_track)

            if len(coords_list) > 1:
                plugins.AntPath(coords_list, color=car_color, weight=5, delay=800).add_to(fg_track)
            fg_track.add_to(m)

        # 2. ยุบรวมวันปกติกล้องเดียวเป็นเลเยอร์เดียว (เพื่อไม่ให้ช่อง checkbox รกบังแผนที่)
        if minor_days:
            group_label = f"🚗 เส้นทางวันอื่นๆ: {plate} (รวม {len(minor_days)} วัน)"
            fg_minor = folium.FeatureGroup(name=group_label)
            for d_info in minor_days:
                day_data = d_info['day_data']
                for i in range(len(day_data)):
                    row = day_data.iloc[i]
                    coords = (row['ละติจูด'], row['ลองจิจูด'])
                    info = (
                        f"<b>ทะเบียน:</b> {plate}<br>"
                        f"<b>วันที่:</b> {row['วันที่']}<br>"
                        f"<b>กล้อง:</b> {row['จุดติดตั้งกล้อง']}<br>"
                        f"<b>เวลา:</b> {row['เวลา']}"
                    )
                    folium.Marker(
                        location=coords,
                        popup=folium.Popup(info, max_width=250),
                        icon=folium.Icon(color='gray', icon='car', prefix='fa')
                    ).add_to(fg_minor)
            fg_minor.add_to(m)

    # 3. Hotzones rings
    hotzone_counts = (
        df_master.groupby(['จุดติดตั้งกล้อง', 'ละติจูด', 'ลองจิจูด'])
        .size().reset_index(name='count')
        .sort_values('count', ascending=False)
    )
    for idx, row in enumerate(hotzone_counts.head(5).itertuples()):
        popup_html = f"<b>📍 พิกัดสถานี:</b> {row.จุดติดตั้งกล้อง}<br><b>ความถี่ผ่านซ้ำ:</b> {row.count} ครั้ง"
        if idx == 0:
            folium.Circle(
                location=[row.ละติจูด, row.ลองจิจูด],
                radius=1500, color='red', fill=True, fill_color='red',
                fill_opacity=0.25, popup=popup_html
            ).add_to(fg_hz_rings)
        else:
            folium.Circle(
                location=[row.ละติจูด, row.ลองจิจูด],
                radius=800, color='yellow', fill=True, fill_color='yellow',
                fill_opacity=0.2, popup=popup_html
            ).add_to(fg_hz_rings)

    # 4. 2D Hideout Rings
    df_r = df_master.reset_index(drop=True)
    same_p = df_r['ทะเบียนรถ'] == df_r['ทะเบียนรถ'].shift(1)
    diff_hrs_s = df_r['Time_diff_hrs'] if 'Time_diff_hrs' in df_r.columns else pd.Series([0.0]*len(df_r))
    mid_lat = (df_r['ละติจูด'] + df_r['ละติจูด'].shift(1)) / 2.0
    mid_lon = (df_r['ลองจิจูด'] + df_r['ลองจิจูด'].shift(1)) / 2.0

    perm_mask = same_p & (diff_hrs_s > 12.0)
    temp_mask = same_p & (diff_hrs_s >= 3.0) & (diff_hrs_s <= 12.0)

    for i in df_r[perm_mask].index:
        folium.Circle(
            location=[mid_lat.iloc[i], mid_lon.iloc[i]],
            radius=2500, color='#4A148C', fill=True, fill_color='#4A148C',
            fill_opacity=0.3, weight=3, dash_array='6, 6',
            popup=f"🏠 กบดานถาวร: หายไป {diff_hrs_s.iloc[i]:.1f} ชม."
        ).add_to(fg_ho_main)

    for i in df_r[temp_mask].index:
        folium.Circle(
            location=[mid_lat.iloc[i], mid_lon.iloc[i]],
            radius=1200, color='#BA55D3', fill=True, fill_color='#BA55D3',
            fill_opacity=0.2, weight=2, dash_array='4, 4',
            popup=f"⏳ จุดพักสินค้าชั่วคราว: หายไป {diff_hrs_s.iloc[i]:.1f} ชม."
        ).add_to(fg_ho_sub)

    # 5. Star/Shield Checkpoints
    if not hotzone_counts.empty:
        main_cp = hotzone_counts.iloc[0]
        folium.Marker(
            location=[main_cp.ละติจูด, main_cp.ลองจิจูด],
            icon=folium.Icon(color='darkred', icon='star', prefix='fa'),
            popup=f"⭐️ จุดสกัดหลัก: {main_cp.จุดติดตั้งกล้อง}"
        ).add_to(fg_cp_main)
        if len(hotzone_counts) > 1:
            sub_cp = hotzone_counts.iloc[1]
            folium.Marker(
                location=[sub_cp.ละติจูด, sub_cp.ลองจิจูด],
                icon=folium.Icon(color='cadetblue', icon='shield', prefix='fa'),
                popup=f"🛡️ จุดสกัดรอง: {sub_cp.จุดติดตั้งกล้อง}"
            ).add_to(fg_cp_sub)

    fg_hz_rings.add_to(m)
    fg_ho_main.add_to(m)
    fg_ho_sub.add_to(m)
    fg_cp_main.add_to(m)
    fg_cp_sub.add_to(m)

    folium.LayerControl(collapsed=True).add_to(m)
    return m


def get_map_html_with_select_all(folium_map):
    css_style = """
    <style>
    .leaflet-control-layers {
        max-height: 350px !important;
        max-width: 500px !important;
        overflow-y: auto !important;
        overflow-x: auto !important;
        box-shadow: 0 4px 14px rgba(0,0,0,0.25) !important;
        border-radius: 8px !important;
        border: 2px solid #2563eb !important;
    }
    .leaflet-control-layers-overlays {
        max-height: 300px !important;
        overflow-y: auto !important;
        overflow-x: auto !important;
        white-space: nowrap !important;
        padding-right: 6px;
    }
    .leaflet-control-layers label {
        white-space: nowrap !important;
        text-overflow: clip !important;
        overflow: visible !important;
        display: block !important;
    }
    /* Horizontal & Vertical Scrollbars customization */
    .leaflet-control-layers::-webkit-scrollbar,
    .leaflet-control-layers-overlays::-webkit-scrollbar {
        width: 7px;
        height: 7px;
    }
    .leaflet-control-layers::-webkit-scrollbar-thumb,
    .leaflet-control-layers-overlays::-webkit-scrollbar-thumb {
        background-color: #2563eb;
        border-radius: 4px;
    }
    .leaflet-control-layers::-webkit-scrollbar-track,
    .leaflet-control-layers-overlays::-webkit-scrollbar-track {
        background-color: #eff6ff;
    }
    .leaflet-control-layers-overlays {
        max-height: 310px !important;
        overflow-y: auto !important;
        padding-right: 4px;
    }
    /* Scrollbar customization for smooth scrolling */
    .leaflet-control-layers::-webkit-scrollbar,
    .leaflet-control-layers-overlays::-webkit-scrollbar {
        width: 7px;
    }
    .leaflet-control-layers::-webkit-scrollbar-thumb,
    .leaflet-control-layers-overlays::-webkit-scrollbar-thumb {
        background-color: #2563eb;
        border-radius: 4px;
    }
    .leaflet-control-layers::-webkit-scrollbar-track,
    .leaflet-control-layers-overlays::-webkit-scrollbar-track {
        background-color: #eff6ff;
    }
    </style>
    """
    folium_map.get_root().html.add_child(folium.Element(css_style))

    toggle_script = """
    <script>
    (function() {
        var _interval = null;
        function addSelectAllToggle() {
            var layerControl = document.querySelector('.leaflet-control-layers-overlays');
            if (!layerControl) return;
            if (document.getElementById('toggle-all-checkbox')) {
                if (_interval) { clearInterval(_interval); _interval = null; }
                return;
            }

            var container = document.createElement('div');
            container.style.padding = '6px 10px';
            container.style.borderBottom = '2px solid #2563eb';
            container.style.marginBottom = '6px';
            container.style.backgroundColor = '#eff6ff';
            container.style.fontWeight = 'bold';
            container.style.borderRadius = '4px';

            var label = document.createElement('label');
            label.style.cursor = 'pointer';
            label.style.fontSize = '13px';
            label.style.color = '#1e3a8a';
            label.style.display = 'flex';
            label.style.alignItems = 'center';

            var checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = 'toggle-all-checkbox';
            checkbox.checked = true;
            checkbox.style.marginRight = '8px';
            checkbox.style.transform = 'scale(1.2)';

            label.appendChild(checkbox);
            label.appendChild(document.createTextNode('☑️ ติ๊ก All เพื่อเลือก/ไม่เลือกทั้งหมด'));
            container.appendChild(label);
            layerControl.insertBefore(container, layerControl.firstChild);

            checkbox.addEventListener('change', function() {
                var inputs = layerControl.querySelectorAll('input[type="checkbox"]');
                inputs.forEach(function(input) {
                    if (input.id !== 'toggle-all-checkbox' && input.checked !== checkbox.checked) {
                        input.click();
                    }
                });
            });

            // Dynamic Red Bold Styling for Highlighted Layers
            setTimeout(function() {
                var labels = layerControl.querySelectorAll('label, span');
                labels.forEach(function(el) {
                    var txt = el.textContent || el.innerText || '';
                    if (txt.indexOf('วันสัญจรขบวน') !== -1 || txt.indexOf('วันสัญจรยาว') !== -1 || txt.indexOf('🚨🔥') !== -1 || txt.indexOf('⭐🔥') !== -1) {
                        el.style.color = '#dc2626';
                        el.style.fontWeight = '800';
                        el.style.backgroundColor = '#fef2f2';
                        el.style.padding = '2px 6px';
                        el.style.borderRadius = '4px';
                        el.style.borderLeft = '3px solid #dc2626';
                    }
                });
            }, 100);

            if (_interval) { clearInterval(_interval); _interval = null; }
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', addSelectAllToggle);
        } else {
            addSelectAllToggle();
        }
        _interval = setInterval(addSelectAllToggle, 300);
        setTimeout(function() {
            if (_interval) { clearInterval(_interval); _interval = null; }
        }, 10000);
    })();
    </script>
    """
    folium_map.get_root().html.add_child(folium.Element(toggle_script))
    return folium_map._repr_html_()
