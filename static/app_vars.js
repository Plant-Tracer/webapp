// Define the variables used

var user = null;                  // not logged in
var apikey = null;                // no API key yet

function findGetParameter(parameterName) {
    var result = null,
        tmp = [];
    var items = location.search.substr(1).split("&");
    for (var index = 0; index < items.length; index++) {
        tmp = items[index].split("=");
        if (tmp[0] === parameterName) result = decodeURIComponent(tmp[1]);
    }
    return result;
}

$( document ).ready( function() {
    $('#adder').click( add_func );
});
