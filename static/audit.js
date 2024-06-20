"use strict";
/* jshint esversion: 8 */
/* global api_key */

////////////////////////////////////////////////////////////////
// page: /audit
// This could fill in the table with search keys; right now we just search for everything
// See https://stackoverflow.com/questions/33682122/datatables-generate-whole-table-from-json

function build_audit_table() {
    let formData = new FormData();
    formData.append("api_key",  api_key); // on the upload form
    fetch(`${API_BASE}api/get-logs`, { method:"POST", body:formData })
        .then((response) => response.json())
        .then((data) => {
            if (data.error!=false){
                $('#message').html('error: '+data.message);
                return;
            }
            let logs = data.logs;
            // get the columns
            var columns = [];
            for (const key in logs[0]) {
                //console.log(`${key}: ${logs{key}}`);
                columns.push( data:key, title:key } );
            }
            // make the data displayable
            $('#audit').DataTable( {
                columns: columns,
                data: logs
            });
        });
}

$( document ).ready( function() {
    build_audit_table();
});
