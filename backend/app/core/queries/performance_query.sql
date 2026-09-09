SELECT
        customer_id,
        created_date,
        city_mapping.correct_city AS city,
        COUNT(DISTINCT customer_ref_id) AS orders_cnt,
        ROUND(toFloat64({inslot_case}), 3) AS InSlot

    FROM
    (
        SELECT
            customer_ref_id,
            source_district_id,
            customer_id,
            created_date,
            create_to_accept_contractual AS T1_C,
            accept_to_arrive_contractual AS T2_C,
            pickup_to_arrive_drop_off_contractual AS T4_C,
            T1_C + T2_C + T4_C AS TRP

        FROM dwh_box.fact_ka
        WHERE created_date >= today()-5
          AND created_date <> today()
          AND status = 'DELIVERED'
          AND customer_id IN ({customer_ids_str})
    ) fact

    INNER JOIN (
        SELECT district_id, correct_city
        FROM s3(
            'https://data-minio.apps.private.okd4.teh-1.snappcloud.io/vbox-dashboards/city_mapping/city_mapping.csv',
            'SLADashboard',
            'zfF3trxxSOwO8dt8f403jp0B8bfDg8CK',
            'CSVWithNames'
        )
    ) city_mapping
    ON fact.source_district_id = city_mapping.district_id

    WHERE city_mapping.correct_city = '{city}'

    GROUP BY customer_id, created_date, city