"use strict";
/* jshint esversion: 8 */
import { $ } from "./utils.js";

////////////////////////////////////////////////////////////////
// page: /audit
// Builds and displays audit log table using vanilla JavaScript

let allLogs = [];
let filteredLogs = [];

function createTableHeader(table, columns) {
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');

    columns.forEach(column => {
        const th = document.createElement('th');
        th.textContent = column;
        th.style.border = '1px solid #ddd';
        th.style.padding = '8px';
        th.style.textAlign = 'left';
        th.style.backgroundColor = '#f2f2f2';
        th.style.cursor = 'pointer';
        th.addEventListener('click', () => sortTable(column));
        headerRow.appendChild(th);
    });

    thead.appendChild(headerRow);
    table.appendChild(thead);
}

function createTableBody(table, logs, columns) {
    // Remove existing tbody if it exists
    const existingTbody = table.querySelector('tbody');
    if (existingTbody) {
        existingTbody.remove();
    }

    const tbody = document.createElement('tbody');

    if (logs.length === 0) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.textContent = 'No logs found';
        cell.colSpan = columns.length;
        cell.style.textAlign = 'center';
        cell.style.padding = '10px';
        row.appendChild(cell);
        tbody.appendChild(row);
    } else {
        logs.forEach(log => {
            const row = document.createElement('tr');
            columns.forEach(column => {
                const cell = document.createElement('td');
                cell.textContent = log[column] !== null && log[column] !== undefined ? log[column] : '';
                cell.style.border = '1px solid #ddd';
                cell.style.padding = '8px';
                row.appendChild(cell);
            });
            tbody.appendChild(row);
        });
    }

    table.appendChild(tbody);
}

let sortColumn = null;
let sortDirection = 'asc';

function sortTable(column) {
    if (sortColumn === column) {
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        sortColumn = column;
        sortDirection = 'asc';
    }

    filteredLogs.sort((a, b) => {
        const aVal = a[column];
        const bVal = b[column];

        if (aVal === null || aVal === undefined) return 1;
        if (bVal === null || bVal === undefined) return -1;

        if (typeof aVal === 'number' && typeof bVal === 'number') {
            return sortDirection === 'asc' ? aVal - bVal : bVal - aVal;
        }

        const aStr = String(aVal).toLowerCase();
        const bStr = String(bVal).toLowerCase();

        if (sortDirection === 'asc') {
            return aStr < bStr ? -1 : aStr > bStr ? 1 : 0;
        } else {
            return aStr > bStr ? -1 : aStr < bStr ? 1 : 0;
        }
    });

    const table = $('#audit').get(0);
    const columns = Object.keys(allLogs[0] || {});
    createTableBody(table, filteredLogs, columns);
}

function filterTable(searchText) {
    if (!searchText) {
        filteredLogs = [...allLogs];
    } else {
        const lowerSearch = searchText.toLowerCase();
        filteredLogs = allLogs.filter(log => {
            return Object.values(log).some(val => {
                return val !== null && val !== undefined &&
                       String(val).toLowerCase().includes(lowerSearch);
            });
        });
    }

    const table = $('#audit').get(0);
    const columns = Object.keys(allLogs[0] || {});
    createTableBody(table, filteredLogs, columns);
}

function build_audit_table() {
    const formData = new FormData();
    formData.append("api_key", api_key);
    fetch(`${API_BASE}api/get-logs`, { method:"POST", body:formData })
        .then((response) => response.json())
        .then((data) => {
            if (data.error !== false) {
                $('#message').html('error: ' + data.message);
                return;
            }

            if (!data.logs || data.logs.length === 0) {
                $('#audit').html('<tbody><tr><td>No logs available</td></tr></tbody>');
                return;
            }

            allLogs = data.logs;
            filteredLogs = [...allLogs];

            const table = $('#audit').get(0);
            if (!table) return;

            // Clear existing table
            table.innerHTML = '';

            // Get column names from first log entry
            const columns = Object.keys(allLogs[0]);

            // Create table header
            createTableHeader(table, columns);

            // Create table body with data
            createTableBody(table, filteredLogs, columns);

            // Set up search functionality
            $('#audit-search').on('input', (e) => {
                filterTable(e.target.value);
            });
        })
        .catch((error) => {
            console.error('Error fetching audit logs:', error);
            $('#message').html('error: Failed to load audit logs');
        });
}

$(document).ready(function() {
    build_audit_table();
});

module.exports = {build_audit_table}
